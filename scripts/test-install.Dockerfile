# The install checks on a clean Ubuntu 24.04, from any computer with Docker (docs/TESTING-PLATFORMS.md):
#
#   docker build -f scripts/test-install.Dockerfile -t kindred-test-install .
#   docker run --rm kindred-test-install            (all checks; or: ... kindred-test-install brain)
#
# Base: Eclipse Temurin's JDK 25 on Ubuntu 24.04 (Gradle runs on Java 25), plus Python and curl.
FROM eclipse-temurin:25-jdk-noble
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv python3-pip curl git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home riverrobin
USER riverrobin
WORKDIR /home/riverrobin/kindred-spirit
COPY --chown=riverrobin . .
ENTRYPOINT ["bash", "scripts/test-install.sh"]
CMD ["all"]
