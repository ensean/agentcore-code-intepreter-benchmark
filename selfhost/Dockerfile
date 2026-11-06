# Sandbox image roughly matching the AgentCore Code Interpreter Python environment
# (Python 3.12, pandas 2.3.1, numpy, matplotlib), with .pyc and matplotlib font cache baked in.
FROM python:3.12-slim

RUN pip install --no-cache-dir pandas==2.3.1 numpy matplotlib \
    && python -m compileall -q /usr/local/lib/python3.12/site-packages || true

RUN groupadd --gid 1500 app && useradd --uid 1500 --gid app --create-home app \
    && install -d -o app -g app /sandbox
USER app
WORKDIR /sandbox
# pre-build matplotlib font cache for the sandbox user
RUN MPLBACKEND=Agg python -c "import matplotlib.pyplot"
CMD ["sleep", "infinity"]
