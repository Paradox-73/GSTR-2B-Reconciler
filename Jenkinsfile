// Build, test and deploy pipeline (DESIGN.md 13.2).
//
// Jenkins host needs: Docker (jenkins user in the docker group), ansible-playbook,
// kubectl with a kubeconfig for the minikube cluster, python3, and the plugins
// Pipeline, Git, GitHub, Docker Pipeline and Credentials Binding.
// Global environment variables (Manage Jenkins > System > Global properties):
//   DOCKERHUB_USER  Docker Hub account the images are pushed to
//   APP_URL         optional, defaults to http://$(minikube ip)

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
                    pytest -q tests/unit
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

        // Week 4: trainer/evaluate.py exits non-zero when a model misses config/quality_gate.yaml.
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
                sh '. .venv/bin/activate && python -m trainer.evaluate --config config/quality_gate.yaml'
            }
        }

        stage('Build') {
            steps {
                sh '''
                    for t in api worker trainer; do
                        docker build --target "$t" \
                            -t "$DOCKERHUB_USER/gstr2b-$t:$SHA" \
                            -t "$DOCKERHUB_USER/gstr2b-$t:latest" .
                    done
                    docker build \
                        -t "$DOCKERHUB_USER/gstr2b-frontend:$SHA" \
                        -t "$DOCKERHUB_USER/gstr2b-frontend:latest" frontend
                '''
            }
        }

        // The trivy-cache volume keeps the vulnerability database between builds.
        // --ignore-unfixed: a CVE with no patched package yet cannot be fixed by us, so it should not block.
        stage('Trivy scan') {
            steps {
                sh '''
                    for i in $IMAGES; do
                        docker run --rm \
                            -v /var/run/docker.sock:/var/run/docker.sock \
                            -v trivy-cache:/root/.cache/ \
                            aquasec/trivy:0.57.1 image \
                            --exit-code 1 --severity CRITICAL --ignore-unfixed --no-progress \
                            "$DOCKERHUB_USER/gstr2b-$i:$SHA"
                    done
                '''
            }
        }

        stage('Push') {
            steps {
                // Moves to the Jenkins Vault plugin in issue #19.
                withCredentials([usernamePassword(credentialsId: 'dockerhub',
                                                  usernameVariable: 'DOCKERHUB_LOGIN',
                                                  passwordVariable: 'DOCKERHUB_TOKEN')]) {
                    sh '''
                        echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_LOGIN" --password-stdin
                        for i in $IMAGES; do
                            docker push "$DOCKERHUB_USER/gstr2b-$i:$SHA"
                            docker push "$DOCKERHUB_USER/gstr2b-$i:latest"
                        done
                    '''
                }
            }
            post {
                always {
                    sh 'docker logout'
                }
            }
        }

        stage('Deploy') {
            steps {
                script {
                    env.DEPLOY_STARTED = 'true'
                }
                sh '''
                    ansible-playbook -i deploy/ansible/inventory/hosts.ini deploy/ansible/deploy.yml \
                        -e image_tag="$SHA" -e dockerhub_user="$DOCKERHUB_USER"
                '''
            }
        }

        stage('Smoke test') {
            when {
                expression { fileExists('scripts/smoke_test.py') }
            }
            steps {
                sh 'python3 scripts/smoke_test.py --base-url "${APP_URL:-http://$(minikube ip)}"'
            }
        }
    }

    post {
        failure {
            script {
                if (env.DEPLOY_STARTED == 'true') {
                    // Only undo Deployments already running this build's image: if migrations
                    // failed, nothing rolled out, and an undo would revert a healthy release.
                    sh '''
                        for d in api worker frontend; do
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
