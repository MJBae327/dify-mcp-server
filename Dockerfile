# Generated by https://smithery.ai. See: https://smithery.ai/docs/config#dockerfile
# Use a Python image
FROM python:3.12-slim

# Set the working directory
WORKDIR /app

# Copy pyproject.toml and uv.lock to the working directory
COPY pyproject.toml uv.lock /app/

# Install the project's dependencies using a package manager that understands pyproject.toml
RUN pip install --no-cache-dir hatchling && hatch build && pip install --no-cache-dir dist/*.whl

# Copy the source files to the container
COPY src/dify_mcp_server /app/src/dify_mcp_server

# Set environment variables, you should provide CONFIG_PATH during container run
ENV CONFIG_PATH=/path/to/config.yaml

# Set the entrypoint
ENTRYPOINT ["dify_mcp_server"]

# The command to run the server
CMD ["run"]