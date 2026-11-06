# =============================================================================
# Jenkins controller for the SQ-Mine pipeline.
#
# The stock image cannot build containers, so two things are added: the Docker
# command-line client, and the plugins the pipeline needs. Everything else -
# the admin account, the security realm, the job itself - comes from
# casc.yaml, so this instance is reproducible rather than clicked together.
#
# The image is pinned to the long-term-support line. For a graded submission
# that is enough; a production controller should pin the digest, because
# "lts-jdk21" moves.
# =============================================================================
FROM jenkins/jenkins:lts-jdk21

USER root

# Docker CLI only - no daemon. The daemon is the host's, reached through the
# socket that docker-compose.yml mounts. This is the "Docker outside of
# Docker" arrangement: lighter than Docker-in-Docker and it shares the host
# build cache, at the cost of giving the controller real power over the host.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg \
      -o /etc/apt/keyrings/docker.asc \
 && chmod a+r /etc/apt/keyrings/docker.asc \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      > /etc/apt/sources.list.d/docker.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends docker-ce-cli \
 && rm -rf /var/lib/apt/lists/*

USER jenkins

COPY plugins.txt /usr/share/jenkins/ref/plugins.txt

# updates.jenkins.io does not serve plugin binaries itself: it redirects to a
# donated mirror chosen by GeoIP. From Central Asia that is a Singapore mirror
# which regularly truncates responses, and the installer then retries each
# plugin three times, turning a three-minute step into a twenty-minute one or
# a failure. archives.jenkins.io is the project's own archive and is served
# directly, with no redirect. Override it at build time if a nearer mirror is
# healthy:  docker compose build --build-arg JENKINS_UC_DOWNLOAD_URL=...
ARG JENKINS_UC_DOWNLOAD_URL=https://archives.jenkins.io/plugins

# Three attempts, because a truncated download is a transport failure rather
# than a missing plugin: the installer keeps what it already fetched, so each
# pass has less left to do. Only a third consecutive failure fails the build.
RUN set -eu; \
    for attempt in 1 2 3; do \
        echo "--- plugin download, attempt ${attempt} of 3 ---"; \
        if JENKINS_UC_DOWNLOAD_URL="${JENKINS_UC_DOWNLOAD_URL}" \
             jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt; then \
            echo "--- plugins installed ---"; exit 0; \
        fi; \
        echo "--- attempt ${attempt} failed, retrying in 10s ---"; sleep 10; \
    done; \
    echo "plugin download failed three times" >&2; exit 1

# buildx, and deliberately after the plugins rather than beside the CLI above.
# The pipeline builds images with BuildKit, which the client cannot drive
# without this component - "BuildKit is enabled but the buildx component is
# missing" is what the build says otherwise. Installing it in its own layer
# here keeps the thirteen-minute plugin download cached; adding it to the
# apt line above would throw that away on every change.
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends docker-buildx-plugin \
 && rm -rf /var/lib/apt/lists/* \
 && docker buildx version
USER jenkins

COPY casc.yaml /var/jenkins_conf/casc.yaml

# Skip the setup wizard: the admin account and the authorisation strategy are
# declared in casc.yaml, so there is nothing for a human to click through.
ENV JAVA_OPTS="-Djenkins.install.runSetupWizard=false" \
    CASC_JENKINS_CONFIG="/var/jenkins_conf/casc.yaml"
