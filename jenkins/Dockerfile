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
RUN JENKINS_UC_DOWNLOAD_URL="${JENKINS_UC_DOWNLOAD_URL}" \
    jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt

COPY casc.yaml /var/jenkins_conf/casc.yaml

# Skip the setup wizard: the admin account and the authorisation strategy are
# declared in casc.yaml, so there is nothing for a human to click through.
ENV JAVA_OPTS="-Djenkins.install.runSetupWizard=false" \
    CASC_JENKINS_CONFIG="/var/jenkins_conf/casc.yaml"
