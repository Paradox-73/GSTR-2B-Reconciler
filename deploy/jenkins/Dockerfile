# Jenkins for this project, configured from casc.yaml (no setup wizard, no clicking).
# Has the tools the Jenkinsfile calls on the controller: docker CLI (+ buildx, so builds use
# BuildKit and its cache; the bare static CLI falls back to the slow legacy builder), kubectl,
# ansible-playbook.
FROM jenkins/jenkins:2.541.3-lts-jdk17

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.3.1.tgz \
      | tar xz -C /tmp \
 && mv /tmp/docker/docker /usr/local/bin/docker && rm -rf /tmp/docker \
 && mkdir -p /usr/local/lib/docker/cli-plugins \
 && curl -fsSLo /usr/local/lib/docker/cli-plugins/docker-buildx \
      https://github.com/docker/buildx/releases/download/v0.19.3/buildx-v0.19.3.linux-amd64 \
 && chmod +x /usr/local/lib/docker/cli-plugins/docker-buildx \
 && curl -fsSLo /usr/local/bin/kubectl https://dl.k8s.io/release/v1.31.4/bin/linux/amd64/kubectl \
 && chmod +x /usr/local/bin/kubectl
RUN python3 -m venv /opt/ansible \
 && /opt/ansible/bin/pip install --no-cache-dir ansible-core==2.17.7 \
 && ln -s /opt/ansible/bin/ansible-playbook /usr/local/bin/ansible-playbook

COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt
COPY casc.yaml /usr/share/jenkins/ref/casc.yaml
ENV CASC_JENKINS_CONFIG=/usr/share/jenkins/ref/casc.yaml \
    JAVA_OPTS="-Djenkins.install.runSetupWizard=false"
# Stays root: it drives the host's Docker through the mounted socket. Local/demo Jenkins only.
