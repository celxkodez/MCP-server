import os
import json
import logging
import httpx
import uvicorn
from typing import Any, Dict, Optional, Sequence
from datetime import datetime
from dotenv import load_dotenv

from fastapi import FastAPI, Request, HTTPException
from sse_starlette.sse import EventSourceResponse
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="GitHub Workflows MCP Server")

# GitHub API configuration
GITHUB_API_BASE = "https://api.github.com"

class GitHubClient:
    """GitHub API client"""
    
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    
    async def request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make a request to GitHub API"""
        url = f"{GITHUB_API_BASE}{endpoint}"
        
        async with httpx.AsyncClient() as client:
            try:
                if method.upper() == "GET":
                    response = await client.get(url, headers=self.headers)
                elif method.upper() == "POST":
                    response = await client.post(url, headers=self.headers, json=data)
                elif method.upper() == "DELETE":
                    response = await client.delete(url, headers=self.headers)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                
                response.raise_for_status()
                
                # Some endpoints return 204 No Content
                if response.status_code == 204:
                    return {"success": True}
                
                return response.json()
            
            except httpx.HTTPStatusError as e:
                logger.error(f"GitHub API error: {e.response.text}")
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"GitHub API error: {e.response.text}"
                )
            except Exception as e:
                logger.error(f"Request error: {str(e)}")
                raise HTTPException(status_code=500, detail=str(e))


def create_mcp_server(github_token: str) -> Server:
    """Create and configure MCP server"""
    
    server = Server("github-workflows-mcp")
    github = GitHubClient(github_token)
    
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools"""
        return [
            Tool(
                name="list_workflows",
                description="List all workflows in a GitHub repository",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Repository owner (username or organization)",
                        },
                        "repo": {
                            "type": "string",
                            "description": "Repository name",
                        },
                    },
                    "required": ["owner", "repo"],
                },
            ),
            Tool(
                name="trigger_workflow",
                description="Trigger a GitHub workflow dispatch event",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Repository owner",
                        },
                        "repo": {
                            "type": "string",
                            "description": "Repository name",
                        },
                        "workflow_id": {
                            "type": "string",
                            "description": "Workflow filename or ID (e.g., 'deploy.yml')",
                        },
                        "ref": {
                            "type": "string",
                            "description": "Git reference (branch or tag)",
                            "default": "main",
                        },
                        "inputs": {
                            "type": "object",
                            "description": "Workflow inputs as key-value pairs",
                            "additionalProperties": True,
                        },
                    },
                    "required": ["owner", "repo", "workflow_id"],
                },
            ),
            Tool(
                name="get_workflow_runs",
                description="Get recent workflow runs for a repository",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Repository owner",
                        },
                        "repo": {
                            "type": "string",
                            "description": "Repository name",
                        },
                        "workflow_id": {
                            "type": "string",
                            "description": "Optional: Filter by specific workflow file",
                        },
                        "status": {
                            "type": "string",
                            "enum": [
                                "completed",
                                "action_required",
                                "cancelled",
                                "failure",
                                "neutral",
                                "skipped",
                                "success",
                                "in_progress",
                                "queued",
                            ],
                            "description": "Optional: Filter by status",
                        },
                        "per_page": {
                            "type": "number",
                            "description": "Number of results (max 100)",
                            "default": 10,
                        },
                    },
                    "required": ["owner", "repo"],
                },
            ),
            Tool(
                name="get_workflow_run",
                description="Get details of a specific workflow run",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Repository owner",
                        },
                        "repo": {
                            "type": "string",
                            "description": "Repository name",
                        },
                        "run_id": {
                            "type": "integer",
                            "description": "Workflow run ID",
                        },
                    },
                    "required": ["owner", "repo", "run_id"],
                },
            ),
            Tool(
                name="cancel_workflow_run",
                description="Cancel a running workflow",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Repository owner",
                        },
                        "repo": {
                            "type": "string",
                            "description": "Repository name",
                        },
                        "run_id": {
                            "type": "integer",
                            "description": "Workflow run ID to cancel",
                        },
                    },
                    "required": ["owner", "repo", "run_id"],
                },
            ),
            Tool(
                name="rerun_workflow",
                description="Re-run a workflow",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Repository owner",
                        },
                        "repo": {
                            "type": "string",
                            "description": "Repository name",
                        },
                        "run_id": {
                            "type": "integer",
                            "description": "Workflow run ID to re-run",
                        },
                    },
                    "required": ["owner", "repo", "run_id"],
                },
            ),
            Tool(
                name="get_workflow_jobs",
                description="Get jobs for a workflow run",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Repository owner",
                        },
                        "repo": {
                            "type": "string",
                            "description": "Repository name",
                        },
                        "run_id": {
                            "type": "integer",
                            "description": "Workflow run ID",
                        },
                    },
                    "required": ["owner", "repo", "run_id"],
                },
            ),
            Tool(
                name="trigger_repository_dispatch",
                description="Trigger a repository_dispatch event",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Repository owner",
                        },
                        "repo": {
                            "type": "string",
                            "description": "Repository name",
                        },
                        "event_type": {
                            "type": "string",
                            "description": "Custom event type name",
                        },
                        "client_payload": {
                            "type": "object",
                            "description": "Custom payload data",
                            "additionalProperties": True,
                        },
                    },
                    "required": ["owner", "repo", "event_type"],
                },
            ),
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> Sequence[TextContent]:
        """Handle tool calls"""
        
        try:
            if name == "list_workflows":
                owner = arguments["owner"]
                repo = arguments["repo"]
                
                data = await github.request(
                    "GET",
                    f"/repos/{owner}/{repo}/actions/workflows"
                )
                
                workflows = [
                    {
                        "id": w["id"],
                        "name": w["name"],
                        "path": w["path"],
                        "state": w["state"],
                        "created_at": w["created_at"],
                        "updated_at": w["updated_at"],
                        "badge_url": w.get("badge_url"),
                    }
                    for w in data.get("workflows", [])
                ]
                
                result = {
                    "total": data.get("total_count", 0),
                    "workflows": workflows,
                }
                
                return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
            elif name == "trigger_workflow":
                owner = arguments["owner"]
                repo = arguments["repo"]
                workflow_id = arguments["workflow_id"]
                ref = arguments.get("ref", "main")
                inputs = arguments.get("inputs", {})
                
                await github.request(
                    "POST",
                    f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
                    data={"ref": ref, "inputs": inputs}
                )
                
                message = f"✅ Workflow '{workflow_id}' triggered successfully in {owner}/{repo} on branch '{ref}'"
                if inputs:
                    message += f"\nInputs: {json.dumps(inputs, indent=2)}"
                
                return [TextContent(type="text", text=message)]
            
            elif name == "get_workflow_runs":
                owner = arguments["owner"]
                repo = arguments["repo"]
                workflow_id = arguments.get("workflow_id")
                status = arguments.get("status")
                per_page = arguments.get("per_page", 10)
                
                endpoint = f"/repos/{owner}/{repo}/actions/runs"
                params = f"?per_page={per_page}"
                if workflow_id:
                    params += f"&workflow_id={workflow_id}"
                if status:
                    params += f"&status={status}"
                
                data = await github.request("GET", endpoint + params)
                
                runs = [
                    {
                        "id": run["id"],
                        "name": run["name"],
                        "status": run["status"],
                        "conclusion": run.get("conclusion"),
                        "created_at": run["created_at"],
                        "updated_at": run["updated_at"],
                        "html_url": run["html_url"],
                        "head_branch": run["head_branch"],
                        "head_sha": run["head_sha"][:7] if run.get("head_sha") else None,
                        "event": run["event"],
                        "actor": run.get("actor", {}).get("login"),
                    }
                    for run in data.get("workflow_runs", [])
                ]
                
                result = {
                    "total": data.get("total_count", 0),
                    "runs": runs,
                }
                
                return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
            elif name == "get_workflow_run":
                owner = arguments["owner"]
                repo = arguments["repo"]
                run_id = arguments["run_id"]
                
                data = await github.request(
                    "GET",
                    f"/repos/{owner}/{repo}/actions/runs/{run_id}"
                )
                
                result = {
                    "id": data["id"],
                    "name": data["name"],
                    "status": data["status"],
                    "conclusion": data.get("conclusion"),
                    "workflow_id": data["workflow_id"],
                    "created_at": data["created_at"],
                    "updated_at": data["updated_at"],
                    "run_started_at": data.get("run_started_at"),
                    "html_url": data["html_url"],
                    "head_branch": data["head_branch"],
                    "head_sha": data["head_sha"],
                    "event": data["event"],
                    "actor": data.get("actor", {}).get("login"),
                    "run_attempt": data.get("run_attempt"),
                }
                
                return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
            elif name == "cancel_workflow_run":
                owner = arguments["owner"]
                repo = arguments["repo"]
                run_id = arguments["run_id"]
                
                await github.request(
                    "POST",
                    f"/repos/{owner}/{repo}/actions/runs/{run_id}/cancel"
                )
                
                return [TextContent(
                    type="text",
                    text=f"✅ Workflow run #{run_id} in {owner}/{repo} cancelled successfully"
                )]
            
            elif name == "rerun_workflow":
                owner = arguments["owner"]
                repo = arguments["repo"]
                run_id = arguments["run_id"]
                
                await github.request(
                    "POST",
                    f"/repos/{owner}/{repo}/actions/runs/{run_id}/rerun"
                )
                
                return [TextContent(
                    type="text",
                    text=f"✅ Workflow run #{run_id} in {owner}/{repo} queued for re-run"
                )]
            
            elif name == "get_workflow_jobs":
                owner = arguments["owner"]
                repo = arguments["repo"]
                run_id = arguments["run_id"]
                
                data = await github.request(
                    "GET",
                    f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs"
                )
                
                jobs = [
                    {
                        "id": job["id"],
                        "name": job["name"],
                        "status": job["status"],
                        "conclusion": job.get("conclusion"),
                        "started_at": job.get("started_at"),
                        "completed_at": job.get("completed_at"),
                        "html_url": job["html_url"],
                        "steps": [
                            {
                                "name": step["name"],
                                "status": step["status"],
                                "conclusion": step.get("conclusion"),
                                "number": step["number"],
                            }
                            for step in job.get("steps", [])
                        ],
                    }
                    for job in data.get("jobs", [])
                ]
                
                result = {
                    "total": data.get("total_count", 0),
                    "jobs": jobs,
                }
                
                return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
            elif name == "trigger_repository_dispatch":
                owner = arguments["owner"]
                repo = arguments["repo"]
                event_type = arguments["event_type"]
                client_payload = arguments.get("client_payload", {})
                
                await github.request(
                    "POST",
                    f"/repos/{owner}/{repo}/dispatches",
                    data={"event_type": event_type, "client_payload": client_payload}
                )
                
                message = f"✅ Repository dispatch event '{event_type}' sent to {owner}/{repo}"
                if client_payload:
                    message += f"\nPayload: {json.dumps(client_payload, indent=2)}"
                
                return [TextContent(type="text", text=message)]
            
            else:
                raise ValueError(f"Unknown tool: {name}")
        
        except Exception as e:
            logger.error(f"Tool execution error: {str(e)}")
            raise RuntimeError(f"Tool execution failed: {str(e)}")
    
    return server


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "github-workflows-mcp"
    }


@app.get("/sse")
async def handle_sse(request: Request):
    """SSE endpoint for MCP - Compatible with Cline"""
    
    # Extract GitHub token
    github_token = request.query_params.get("token")
    
    if not github_token:
        auth_header = request.headers.get("authorization")
        if auth_header:
            github_token = auth_header.replace("Bearer ", "").strip()
    
    if not github_token:
        github_token = os.getenv("GITHUB_TOKEN")
    
    if not github_token:
        logger.error("❌ No GitHub token provided")
        raise HTTPException(
            status_code=401,
            detail="No GitHub token provided"
        )
    
    logger.info("=" * 60)
    logger.info("🔄 NEW MCP SSE CONNECTION ATTEMPT")
    logger.info(f"Headers: {dict(request.headers)}")
    logger.info(f"Method: {request.method}")
    logger.info(f"Path: {request.url.path}")
    logger.info("=" * 60)
    
    # Create MCP server
    mcp_server = create_mcp_server(github_token)
    
    # CRITICAL: Path must be exactly "/sse" to match the endpoint
    sse = SseServerTransport("/sse")
    
    try:
        logger.info("📡 Attempting to connect SSE transport...")
        
        async with sse.connect_sse(
            request.scope,
            request.receive,
            request._send
        ) as (read_stream, write_stream):
            
            logger.info("✅ SSE transport connected successfully!")
            logger.info("🚀 Starting MCP server...")
            
            # Create initialization options
            init_options = mcp_server.create_initialization_options()
            logger.info(f"Init options: {init_options}")
            
            # Run MCP server
            await mcp_server.run(
                read_stream,
                write_stream,
                init_options
            )
            
            logger.info("✅ MCP server session completed normally")
            
    except Exception as e:
        logger.error(f"❌ MCP ERROR: {type(e).__name__}: {e}", exc_info=True)
        raise


@app.post("/sse")
async def handle_sse_post(request: Request):
    """Handle POST requests to SSE endpoint"""
    try:
        body = await request.json()
        logger.info(f"📨 Received POST to /sse: {json.dumps(body, indent=2)}")
        
        return {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "result": {"status": "received"}
        }
        
    except Exception as e:
        logger.error(f"❌ POST handler error: {e}", exc_info=True)
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": str(e)}
        }
# Remove the /sse/messages endpoints since SSE transport handles messages at /sse
# @app.post("/sse/messages")  <-- DELETE THIS

@app.get("/")
async def root():
    """Root endpoint with server info"""
    return {
        "name": "GitHub Workflows MCP Server",
        "version": "1.0.0",
        "mcp_endpoint": "http://localhost:8000/sse",
        "transport": "SSE",
        "endpoints": {
            "health": "/health",
            "sse": "/sse (GET for SSE connection, POST for messages)"
        },
        "status": "running"
    }

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        reload=True
    )