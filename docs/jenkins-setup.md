# Running the pipeline, and the evidence it produces

Everything here runs on one laptop. The only prerequisite is a working Docker
daemon — Docker Desktop on macOS or Windows, Docker Engine on Linux — with
roughly 4 GB of free disk and ports 8080 and 50000 unused.

Nothing has to be configured through the Jenkins interface. The controller is
declared in `jenkins/casc.yaml`, the job is created from it, and the pipeline
is read from `Jenkinsfile` in this repository.

---

## 1. Bring the controller up

```bash
git clone https://github.com/Aldidiyar/sqmine.git
cd sqmine
docker compose up -d --build
```

The first build downloads the Jenkins image and installs thirteen plugins, so
it takes three to six minutes. Watch it finish:

```bash
docker compose logs -f jenkins
```

Wait for `Jenkins is fully up and running`, then press Ctrl-C.

Open <http://localhost:8080> and sign in as **admin / admin**. To use a
different password, set `JENKINS_ADMIN_PASSWORD` before `docker compose up`.

> **Screenshot 1 — the dashboard.** The `sqmine-ci` job is already listed. No
> one created it by hand; Configuration as Code did, which is the point worth
> capturing.

---

## 2. Run the pipeline

Open **sqmine-ci** and press **Build Now**. The first run takes four to eight
minutes, almost all of it building the two images; later runs reuse the layer
cache and finish in about a minute.

Seven stages run in order:

| Stage | What it proves |
|---|---|
| Checkout | the commit under test is identified in the log |
| Build the test image | the package builds as a wheel and installs |
| Quality gate and unit tests | ruff, mypy and 171 tests pass; JUnit report collected |
| Build the runtime image | the shipped image builds and is labelled |
| Smoke-test the runtime image | the entry point starts and does not run as root |
| Push to the registry | *optional*, needs the `dockerhub` credential |
| Deploy to Kubernetes | *optional*, needs kubectl and a cluster |

> **Screenshot 2 — Stage View.** The row of green stages with their timings.
> This is the single most useful image for the report.
>
> **Screenshot 3 — Console Output.** Scroll to the end of the quality-gate
> stage, where `--- gate passed ---` appears after the coverage table.
>
> **Screenshot 4 — Test Result.** The left-hand menu of the build has a *Test
> Result* entry: 171 tests, zero failures. After two or more builds the job
> page also shows the test-trend graph.

---

## 3. Check what was produced

```bash
docker images | grep sqmine
docker run --rm aldidiyar/sqmine:latest --version
docker run --rm aldidiyar/sqmine:latest --help
```

> **Screenshot 5 — the built image.** The image list and the version the
> container prints, side by side in one terminal.

---

## 4. Optional: push to Docker Hub

1. Create an access token at <https://hub.docker.com/settings/security>.
2. In Jenkins: **Manage Jenkins → Credentials → System → Global → Add
   Credentials**. Kind *Username with password*, username is the Docker Hub
   account, password is the token, **ID must be `dockerhub`**.
3. Run **Build with Parameters** and tick `PUSH_IMAGE`. Set
   `IMAGE_REPOSITORY` to `<your-account>/sqmine`.

> **Screenshot 6 — the push.** The green *Push to the registry* stage, and the
> tags page on Docker Hub showing the build number.

---

## 5. Optional: deploy to Kubernetes

The controller started by `docker-compose.yml` has no `kubectl` and no route
to a cluster running on the host, so on a laptop the deployment is run from
the host instead. The pipeline stage exists for a real cluster, where the
agent has both.

```bash
minikube start
minikube image load aldidiyar/sqmine:latest   # skip if the image was pushed
./k8s/deploy.sh
```

The script applies the manifests, generates a development pseudonymisation
key if the cluster has none, points the CronJob at the image and triggers one
run immediately — a CronJob scheduled for 02:17 proves nothing at four in the
afternoon.

```bash
kubectl -n sqmine get cronjob,job,pod
kubectl -n sqmine logs job/<the job the script named>
```

> **Screenshot 7 — the cluster.** The resource list and the job output showing
> `8/8 rows accepted`.

---

## Shutting down

```bash
docker compose down            # keeps the Jenkins volume and the job history
docker compose down -v         # removes it, so the next start is clean again
```

---

## If something goes wrong

**`Cannot connect to the Docker daemon` inside a build.** The controller talks
to the host daemon through the mounted socket. Check that
`/var/run/docker.sock` exists on the host and that the Docker daemon is
running; on Linux also check that the compose service still has `user: root`.

**Port 8080 is already in use.** Change the published port in
`docker-compose.yml` to `"8081:8080"` and set `JENKINS_URL` to match.

**The job is missing after a restart.** Configuration as Code re-creates it on
boot. If it is still absent, the controller failed to read `casc.yaml` —
`docker compose logs jenkins | grep -i casc` names the reason.

**Plugin installation fails behind a proxy.** `jenkins-plugin-cli` honours
`HTTP_PROXY` and `HTTPS_PROXY`; pass them as build arguments.

**The gate stage fails on formatting.** `ruff format --check` also formats
Python code blocks inside Markdown. Run `ruff format .` locally and commit the
result.
