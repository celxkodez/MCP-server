# workflows-mcp-server

## Overview

`workflows-mcp-server` is a backend service designed to manage and orchestrate workflow processes for enterprise applications. It provides APIs for workflow creation, execution, monitoring, and integration with other systems.


## Getting Started

### Installation

```bash
git clone https://github.com/your-org/workflows-mcp-server.git
cd workflows-mcp-server
python3 -m venv venv
source venv/bin/activate
pipe install -r requirement.txt

cp .env.example .env
```

### Configuration

Update the `.env` file with your github tokens and other environment settings.

### Running the Server

```bash
python main.py
```

### Server Health Checks

you can quickly do a health checks but it's optional

```bash
curl http://localhost:8000/health
```