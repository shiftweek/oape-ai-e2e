FROM registry.access.redhat.com/ubi9/go-toolset

# Install system dependencies required by operator tooling
USER 0
RUN dnf install -y \
        git \
        make && \
    # Install Go toolchain
    curl -fsSL https://go.dev/dl/go1.23.6.linux-amd64.tar.gz | tar -C /usr/local -xz && \
    # Install GitHub CLI
    dnf install -y 'dnf-command(config-manager)' && \
    dnf config-manager --add-repo https://cli.github.com/packages/rpm/gh-cli.repo && \
    dnf install -y gh && \
    dnf clean all

ENV PATH="/usr/local/go/bin:${PATH}"

WORKDIR /app

# Install Python dependencies
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code and config
COPY server/server.py server/config.json ./

# Copy plugins directory
# server.py resolves: Path(__file__).parent.parent / "plugins" / "oape"
# With __file__=/app/server.py, parent.parent=/, so it expects /plugins/oape
COPY plugins /plugins

USER 1001

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
