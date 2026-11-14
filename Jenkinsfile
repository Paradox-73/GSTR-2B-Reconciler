// Build, test and deploy pipeline (DESIGN.md 13.2).
//
// Jenkins host needs: Docker (jenkins user in the docker group), ansible-playbook,
// kubectl with a kubeconfig for the minikube cluster, python3, and the plugins
// Pipeline, Git, GitHub, Docker Pipeline and Credentials Binding.
// Global environment variables (Manage Jenkins > System > Global properties):
//   DOCKERHUB_USER  Docker Hub account the images are pushed to
//   APP_URL         optional, defaults to http://$(minikube ip)
//   APP_USE_VAULT   optional, "true" once roles/vault ran: deploys deploy/k8s-vault
//   REGISTRY        optional, empty = Docker Hub. A local registry (e.g. localhost:5001, with
//                   DOCKERHUB_USER=localhost:5001) works for an offline demo or a test run

pipeline {
    agent any

    triggers {
        githubPush()
    }

    options {
        skipDefaultCheckout()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timeout(time: 45, unit: 'MINUTES')
    }

    environment {
        NAMESPACE = 'gstr2b'
        IMAGES = 'api worker trainer frontend'
        PIP_DISABLE_PIP_VERSION_CHECK = '1'
    }

    stages {
        stage('Checkout') {
            steps {
                script {
                    def scmVars = checkout scm
                    env.SHA = scmVars.GIT_COMMIT.substring(0, 7)
                    if (!env.DOCKERHUB_USER) {
                        error 'Set the DOCKERHUB_USER global environment variable in Jenkins.'
                    }
                }
            }
        }

        // The venv sits in the workspace, so the next stages reuse it.
        stage('Lint + unit tests') {
            agent {
                docker {
                    image 'python:3.12-slim'
                    reuseNode true
                }
            }
            environment {
                PIP_CACHE_DIR = "${WORKSPACE}/.pip-cache"
            }
            steps {
                sh '''
                    python -m venv .venv
                    . .venv/bin/activate
                    pip install -q -r requirements-dev.txt
                    ruff check .
                    pytest -q tests/unit tests/api
                '''
            }
        }

        stage('Golden-set tests') {
            agent {
                docker {
                    image 'python:3.12-slim'
                    reuseNode true
                }
            }
            steps {
                sh '. .venv/bin/activate && pytest -q tests/golden'
            }
        }

        // Exits non-zero when the model misses config/quality_gate.yaml on the golden set.
        stage('Model quality gate') {
            when {
                beforeAgent true
                expression { fileExists('trainer/evaluate.py') }
            }
            agent {
                docker {
                    image 'python:3.12-slim'
                    reuseNode true
                }
            }
            steps {
                sh '. .venv/bin/activate && python -m trainer.evaluate'
            }
        }

        stage('Build') {
            steps {
                sh '''
                    for t in api worker trainer; do
                        docker build --target "$t" --build-arg APP_VERSION="$SHA" \
                            -t "$DOCKERHUB_USER/gstr2b-$t:$SHA" \
                            -t "$DOCKERHUB_USER/gstr2b-$t:latest" .
                    done
                    docker build --build-arg APP_VERSION="$SHA" \
                        -t "$DOCKERHUB_USER/gstr2b-frontend:$SHA" \
                        -t "$DOCKERHUB_USER/gstr2b-frontend:latest" frontend
                '''
            }
        }

        // The trivy-cache volume keeps the vulnerability database between builds.
        // --ignore-unfixed: a CVE with no patched package yet cannot be fixed by us, so it should not block.
        stage('Trivy scan') {
            steps {
                // Per image: a CycloneDX SBOM (every package in the image, kept with the build),
                // then the gate: any fixable CRITICAL CVE fails the build. Trivy runs in its own
                // container, so the SBOM comes out on stdout and lands in this workspace.
                sh '''
                    trivy_image() {
                        img=$1; shift
                        docker run --rm \
                            -v /var/run/docker.sock:/var/run/docker.sock \
                            -v trivy-cache:/root/.cache/ \
                            aquasec/trivy:0.57.1 image --no-progress "$@" "$img"
                    }
                    rm -f sbom-*.cdx.json
                    for i in $IMAGES; do
                        trivy_image "$DOCKERHUB_USER/gstr2b-$i:$SHA" --quiet --format cyclonedx > "sbom-$i.cdx.json"
                        trivy_image "$DOCKERHUB_USER/gstr2b-$i:$SHA" --exit-code 1 --severity CRITICAL --ignore-unfixed
                    done
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'sbom-*.cdx.json', allowEmptyArchive: true
                }
            }
        }

        stage('Push') {
            steps {
                // The Docker Hub token comes from Vault (Jenkins Vault plugin, AppRole login set up
                // in deploy/jenkins/casc.yaml); Jenkins itself stores no token. Only the token is
                // read: the plugin masks every value it reads, and a masked user would also hide
                // the image names in this log.
                withVault(vaultSecrets: [[path: 'secret/jenkins/dockerhub', engineVersion: 2,
                                          secretValues: [[envVar: 'DOCKERHUB_TOKEN', vaultKey: 'token']]]]) {
                    sh '''
                        echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USER" --password-stdin $REGISTRY
                        for i in $IMAGES; do
                            docker push "$DOCKERHUB_USER/gstr2b-$i:$SHA"
                            docker push "$DOCKERHUB_USER/gstr2b-$i:latest"
                        done
                    '''
                }
            }
            post {
                always {
                    sh 'docker logout $REGISTRY'
                }
            }
        }

        stage('Deploy') {
            steps {
                // What each Deployment ran before this build, so the rollback can tell whether
                // this build actually rolled anything out (a rebuild of the live sha doesn't).
                sh '''
                    kubectl -n "$NAMESPACE" get deployment api worker frontend \
                        -o jsonpath='{range .items[*]}{.metadata.name}={.spec.template.spec.containers[0].image}{"\\n"}{end}' \
                        > pre-deploy-images.txt || true
                    cat pre-deploy-images.txt
                '''
                script {
                    env.DEPLOY_STARTED = 'true'
                }
                sh '''
                    ansible-playbook -i deploy/ansible/inventory/hosts.ini deploy/ansible/deploy.yml \
                        -e image_tag="$SHA" -e dockerhub_user="$DOCKERHUB_USER" \
                        -e app_use_vault="${APP_USE_VAULT:-false}"
                '''
                script {  // minikube lives on the host, not in the smoke test's container
                    env.APP_URL = env.APP_URL ?: "http://${sh(script: 'minikube ip', returnStdout: true).trim()}"
                }
            }
        }

        // Runs on the Jenkins machine, not in a docker agent: in a test run the agent container
        // got neither APP_URL nor the credential variables. Login comes from the 'smoke-user'
        // credential (the app's ADMIN_EMAIL / ADMIN_PASSWORD).
        stage('Smoke test') {
            steps {
                withCredentials([usernamePassword(credentialsId: 'smoke-user',
                                                  usernameVariable: 'SMOKE_EMAIL',
                                                  passwordVariable: 'SMOKE_PASSWORD')]) {
                    sh '''
                        python3 -m venv .smoke-venv
                        . .smoke-venv/bin/activate
                        pip install -q httpx==0.28.1 pandas==3.0.6
                        python scripts/smoke_test.py --base-url "$APP_URL"
                    '''
                }
            }
        }
    }

    post {
        failure {
            script {
                if (env.DEPLOY_STARTED == 'true') {
                    // Only undo Deployments this build moved onto its image. If migrations failed,
                    // nothing rolled out; if a Deployment was already on this sha before the deploy
                    // (a rebuild), an undo would revert the healthy release that's live.
                    sh '''
                        for d in api worker frontend; do
                            before=$(sed -n "s/^$d=//p" pre-deploy-images.txt 2>/dev/null)
                            case "$before" in
                                *":$SHA")
                                    echo "skipped rollback of $d: already on $SHA before this deploy"
                                    continue
                                    ;;
                            esac
                            img=$(kubectl -n "$NAMESPACE" get deployment "$d" \
                                -o jsonpath='{.spec.template.spec.containers[0].image}')
                            case "$img" in
                                *":$SHA")
                                    kubectl -n "$NAMESPACE" rollout undo "deployment/$d" \
                                        || echo "no earlier revision of $d to roll back to"
                                    ;;
                            esac
                        done
                    '''
                }
            }
        }
    }
}
