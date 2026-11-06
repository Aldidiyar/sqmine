// =============================================================================
// SQ-Mine continuous integration and delivery pipeline.
//
// The shape of this file follows one rule: every stage either produces an
// artefact the next stage consumes, or refuses to let the build continue.
// Nothing here is decorative.
//
//   Checkout -> test image -> quality gate -> runtime image -> smoke test
//            -> push (optional) -> deploy to Kubernetes (optional)
//
// The agent needs a Docker client with access to a daemon; docker-compose.yml
// in this repository brings up a Jenkins that has one.
// =============================================================================

pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 40, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20', artifactNumToKeepStr: '10'))
        disableConcurrentBuilds()
    }

    parameters {
        booleanParam(
            name: 'PUSH_IMAGE', defaultValue: false,
            description: 'Push the runtime image to the registry. Requires a username/password credential with the id "dockerhub".')
        booleanParam(
            name: 'DEPLOY_TO_K8S', defaultValue: false,
            description: 'Apply k8s/ to whatever cluster kubectl is configured for. Requires kubectl on the agent.')
        string(
            name: 'IMAGE_REPOSITORY', defaultValue: 'aldidiyar/sqmine',
            description: 'Registry repository for the runtime image.')
    }

    environment {
        TEST_IMAGE     = "sqmine-test:${env.BUILD_NUMBER}"
        RUNTIME_IMAGE  = "${params.IMAGE_REPOSITORY}:${env.BUILD_NUMBER}"
        LATEST_IMAGE   = "${params.IMAGE_REPOSITORY}:latest"
        GATE_CONTAINER = "sqmine-gate-${env.BUILD_NUMBER}"
        DOCKER_BUILDKIT = '1'
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
                sh 'git --no-pager log -1 --pretty="commit %h by %an: %s"'
                script {
                    env.VCS_REF    = sh(returnStdout: true, script: 'git rev-parse --short HEAD').trim()
                    env.BUILD_DATE = sh(returnStdout: true, script: 'date -u +%Y-%m-%dT%H:%M:%SZ').trim()
                }
            }
        }

        stage('Build the test image') {
            steps {
                // --network=host for the same reason the controller image
                // is built that way: large downloads inside a build container
                // on the default bridge were being truncated on this host.
                sh 'docker build --network=host --target test --tag "$TEST_IMAGE" .'
            }
        }

        stage('Quality gate and unit tests') {
            steps {
                // No --rm here, and that is the whole trick. The container has
                // to outlive its own failure, because the JUnit report is
                // written inside it and a removed container takes the report
                // with it. Copy first, then delete, then fail.
                sh '''
                    set -eu
                    rm -rf reports && mkdir -p reports
                    rc=0
                    docker run --name "$GATE_CONTAINER" "$TEST_IMAGE" run-gate || rc=$?
                    docker cp "$GATE_CONTAINER:/reports/." reports/ 2>/dev/null || true
                    docker rm -f "$GATE_CONTAINER" >/dev/null 2>&1 || true
                    ls -l reports || true
                    exit $rc
                '''
            }
            post {
                always {
                    junit testResults: 'reports/junit.xml', allowEmptyResults: true
                    archiveArtifacts artifacts: 'reports/*.xml',
                                     allowEmptyArchive: true, fingerprint: true
                }
            }
        }

        stage('Build the runtime image') {
            steps {
                sh '''
                    set -eu
                    docker build --network=host --target runtime \
                        --build-arg VCS_REF="$VCS_REF" \
                        --build-arg BUILD_DATE="$BUILD_DATE" \
                        --tag "$RUNTIME_IMAGE" \
                        --tag "$LATEST_IMAGE" \
                        .
                    docker image inspect "$RUNTIME_IMAGE" \
                        --format 'runtime image {{.RepoTags}} {{.Size}} bytes'
                '''
            }
        }

        stage('Smoke-test the runtime image') {
            steps {
                // Two things worth failing a release over: the entry point does
                // not start, and the image ships a root process.
                sh '''
                    set -eu
                    docker run --rm "$RUNTIME_IMAGE" --version
                    uid="$(docker run --rm --entrypoint id "$RUNTIME_IMAGE" -u)"
                    if [ "$uid" = "0" ]; then
                        echo "the runtime image runs as root" >&2
                        exit 1
                    fi
                    echo "runtime image runs as uid $uid"
                '''
            }
        }

        stage('Push to the registry') {
            when { expression { return params.PUSH_IMAGE } }
            steps {
                withCredentials([usernamePassword(
                        credentialsId: 'dockerhub',
                        usernameVariable: 'REGISTRY_USER',
                        passwordVariable: 'REGISTRY_TOKEN')]) {
                    sh '''
                        set -eu
                        echo "$REGISTRY_TOKEN" | docker login -u "$REGISTRY_USER" --password-stdin
                        docker push "$RUNTIME_IMAGE"
                        docker push "$LATEST_IMAGE"
                        docker logout
                    '''
                }
            }
        }

        stage('Deploy to Kubernetes') {
            when { expression { return params.DEPLOY_TO_K8S } }
            steps {
                // Deployment here means a batch workload, not a long-running
                // service: sqmine processes a corpus and exits. A CronJob is
                // the honest Kubernetes object for that, and the verification
                // run below is a real job, not a readiness probe on a process
                // that would be idle anyway.
                sh '''
                    set -eu
                    kubectl apply -k k8s/

                    # The pseudonymisation key is not in the manifests and
                    # never will be. On a development cluster the pipeline
                    # generates one the first time; a real deployment injects
                    # it from a secret manager and this branch never runs.
                    if ! kubectl -n sqmine get secret sqmine-pseudonymisation-key >/dev/null 2>&1; then
                        echo "generating a development pseudonymisation key"
                        kubectl -n sqmine create secret generic sqmine-pseudonymisation-key \
                            --from-literal=pseudonymisation.key="$(head -c 32 /dev/urandom | base64 | tr -d '\n')"
                    fi

                    kubectl -n sqmine set image cronjob/sqmine-nightly-ingest \
                        sqmine="$RUNTIME_IMAGE"
                    kubectl -n sqmine delete job "sqmine-verify-$BUILD_NUMBER" --ignore-not-found
                    kubectl -n sqmine create job "sqmine-verify-$BUILD_NUMBER" \
                        --from=cronjob/sqmine-nightly-ingest
                    kubectl -n sqmine wait --for=condition=complete --timeout=180s \
                        "job/sqmine-verify-$BUILD_NUMBER"
                    kubectl -n sqmine logs "job/sqmine-verify-$BUILD_NUMBER" --tail=30
                '''
            }
        }
    }

    post {
        always {
            sh '''
                docker rm -f "$GATE_CONTAINER" >/dev/null 2>&1 || true
                docker rmi -f "$TEST_IMAGE" >/dev/null 2>&1 || true
            '''
        }
        success {
            echo "Build ${env.BUILD_NUMBER} green. Runtime image: ${env.RUNTIME_IMAGE}"
        }
        failure {
            echo "Build ${env.BUILD_NUMBER} failed. The stage view shows which gate stopped it."
        }
        cleanup {
            cleanWs()
        }
    }
}
