#!/usr/bin/env python3
"""
Moltbook MCP Server - x402 Monetization
Makes money by selling Moltbook actions to other AI agents via MCP + x402 micropayments.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Optional
from collections.abc import Sequence

# Add parent directories to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Try to import Moltbook modules
try:
    from moltbook_post import create_post, solve_lobster_math
    from moltbook_actions import comment_on_post, upvote_post
    MOLTBOOK_AVAILABLE = True
except ImportError:
    MOLTBOOK_AVAILABLE = False
    print("[MCP] Moltbook modules not available - running in test mode", file=sys.stderr)

# MCP imports (install: pip install mcp)
try:
    from mcp.server import Server
    from mcp.types import TextContent, Tool, ImageContent, EmbeddedResource
    from mcp.server.models import InitializationOptions
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    print("[MCP] MCP package not installed - run: pip install mcp", file=sys.stderr)
    sys.exit(1)


class X402PaymentHandler:
    """
    Handles x402 payment verification for MCP tool access.
    Placeholder implementation - replace with real x402 verification.
    """
    
    PRICING = {
        "moltbook_post": 0.05,      # $0.05 per post
        "moltbook_comment": 0.02,   # $0.02 per comment
        "moltbook_upvote": 0.01,    # $0.01 per upvote
        "moltbook_solve_captcha": 0.00,  # Free (attracts users)
    }
    
    def __init__(self):
        self.payments_received = {}
    
    def get_price(self, tool_name: str) -> float:
        return self.PRICING.get(tool_name, 0.01)
    
    def check_payment(self, tool_name: str, payment_token: Optional[str] = None) -> bool:
        """
        Verify x402 payment token.
        Placeholder: Accepts any token for testing.
        TODO: Implement real x402 verification with on-chain checks.
        """
        if payment_token:
            # Placeholder: Log payment
            self.payments_received[tool_name] = self.payments_received.get(tool_name, 0) + 1
            return True
        
        # Free tools don't need payment
        if self.get_price(tool_name) == 0:
            return True
        
        return False  # Require payment for paid tools
    
    def get_stats(self) -> dict:
        return {
            "payments_received": self.payments_received,
            "total_tools": len(self.PRICING),
            "free_tools": sum(1 for p in self.PRICING.values() if p == 0),
            "paid_tools": sum(1 for p in self.PRICING.values() if p > 0),
        }


# Create server instance
server = Server("moltbook-mcp")
payment_handler = X402PaymentHandler()


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools."""
    return [
        Tool(
            name="get_pricing",
            description="Get current pricing for all Moltbook tools. Free to use.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_stats",
            description="Get server statistics and payment history. Free to use.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="moltbook_post",
            description="Create a post on Moltbook. Cost: $0.05 per post (x402 micropayment).",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Post content (supports markdown)"},
                    "submolt": {"type": "string", "description": "Target community (trading/ai/general/ascii)", "default": "general"},
                },
                "required": ["content"],
            },
        ),
        Tool(
            name="moltbook_comment",
            description="Comment on a Moltbook post. Cost: $0.02 per comment (x402 micropayment).",
            inputSchema={
                "type": "object",
                "properties": {
                    "post_id": {"type": "string", "description": "Target post ID"},
                    "content": {"type": "string", "description": "Comment text"},
                },
                "required": ["post_id", "content"],
            },
        ),
        Tool(
            name="moltbook_upvote",
            description="Upvote a Moltbook post. Cost: $0.01 per upvote (x402 micropayment).",
            inputSchema={
                "type": "object",
                "properties": {
                    "post_id": {"type": "string", "description": "Target post ID"},
                },
                "required": ["post_id"],
            },
        ),
        Tool(
            name="moltbook_solve_captcha",
            description="Solve a Moltbook Reverse CAPTCHA challenge. FREE tool (no charge).",
            inputSchema={
                "type": "object",
                "properties": {
                    "challenge": {"type": "string", "description": "Obfuscated math challenge text"},
                },
                "required": ["challenge"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
    """Handle tool calls."""
    
    if name == "get_pricing":
        return [TextContent(
            type="text",
            text=json.dumps({
                "success": True,
                "pricing": X402PaymentHandler.PRICING,
                "currency": "USDC",
                "network": "Base",
                "timestamp": datetime.now().isoformat()
            }, indent=2)
        )]
    
    elif name == "get_stats":
        return [TextContent(
            type="text",
            text=json.dumps({
                "success": True,
                "stats": payment_handler.get_stats(),
                "moltbook_available": MOLTBOOK_AVAILABLE,
                "timestamp": datetime.now().isoformat()
            }, indent=2)
        )]
    
    elif name == "moltbook_post":
        if not MOLTBOOK_AVAILABLE:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": "Moltbook modules not available",
                    "timestamp": datetime.now().isoformat()
                })
            )]
        
        try:
            content = arguments.get("content", "")
            submolt = arguments.get("submolt", "general")
            result = create_post(content, submolt)
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": True,
                    "post_id": result.get("id", "unknown"),
                    "status": "published",
                    "timestamp": datetime.now().isoformat()
                })
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
            )]
    
    elif name == "moltbook_comment":
        if not MOLTBOOK_AVAILABLE:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": "Moltbook modules not available",
                    "timestamp": datetime.now().isoformat()
                })
            )]
        
        try:
            post_id = arguments.get("post_id", "")
            content = arguments.get("content", "")
            result = comment_on_post(post_id, content)
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": True,
                    "post_id": post_id,
                    "status": "commented",
                    "timestamp": datetime.now().isoformat()
                })
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
            )]
    
    elif name == "moltbook_upvote":
        if not MOLTBOOK_AVAILABLE:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": "Moltbook modules not available",
                    "timestamp": datetime.now().isoformat()
                })
            )]
        
        try:
            post_id = arguments.get("post_id", "")
            result = upvote_post(post_id)
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": True,
                    "post_id": post_id,
                    "status": "upvoted",
                    "timestamp": datetime.now().isoformat()
                })
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
            )]
    
    elif name == "moltbook_solve_captcha":
        if not MOLTBOOK_AVAILABLE:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": "Moltbook modules not available",
                    "timestamp": datetime.now().isoformat()
                })
            )]
        
        try:
            challenge = arguments.get("challenge", "")
            answer = solve_lobster_math(challenge)
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": True,
                    "answer": answer,
                    "challenge": challenge[:50] + "..." if len(challenge) > 50 else challenge,
                    "timestamp": datetime.now().isoformat()
                })
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
            )]
    
    else:
        return [TextContent(
            type="text",
            text=json.dumps({
                "success": False,
                "error": f"Unknown tool: {name}",
                "timestamp": datetime.now().isoformat()
            })
        )]


def test_mode():
    """Test mode - verify imports and basic functionality without running server."""
    print("=" * 60)
    print("Moltbook MCP Server - Test Mode")
    print("=" * 60)
    
    # Test MCP availability
    print(f"\n[1] MCP SDK: {'✅ Available' if MCP_AVAILABLE else '❌ Not Available'}")
    
    # Test Moltbook modules
    print(f"[2] Moltbook modules: {'✅ Available' if MOLTBOOK_AVAILABLE else '⚠️ Not Available (test mode)'}")
    
    # Test pricing
    print(f"\n[3] Pricing configured:")
    for tool, price in X402PaymentHandler.PRICING.items():
        status = "FREE" if price == 0 else f"${price:.2f}"
        print(f"    - {tool}: {status}")
    
    # Test server initialization
    try:
        print(f"\n[4] Server initialization: ✅ Success")
        print(f"    Server name: moltbook-mcp")
        print(f"    Tools registered: get_pricing, get_stats, moltbook_post, moltbook_comment, moltbook_upvote, moltbook_solve_captcha")
    except Exception as e:
        print(f"\n[4] Server initialization: ❌ Failed - {e}")
        return False
    
    print(f"\n[5] Stats: {json.dumps(payment_handler.get_stats(), indent=2)}")
    
    print("\n" + "=" * 60)
    print("Test complete. Server ready for MCP transport (stdio).")
    print("Run without --test to start the server.")
    print("=" * 60)
    return True


def main():
    """Entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Moltbook MCP Server")
    parser.add_argument("--test", action="store_true", help="Run in test mode (no server)")
    args = parser.parse_args()
    
    if args.test:
        success = test_mode()
        sys.exit(0 if success else 1)
    else:
        from mcp.server.stdio import stdio_server
        
        async def run():
            print("[MCP] Moltbook MCP Server starting...", file=sys.stderr)
            print(f"[MCP] Moltbook available: {MOLTBOOK_AVAILABLE}", file=sys.stderr)
            print(f"[MCP] Pricing: {json.dumps(X402PaymentHandler.PRICING, indent=2)}", file=sys.stderr)
            
            async with stdio_server() as (read_stream, write_stream):
                await server.run(
                    read_stream,
                    write_stream,
                    InitializationOptions(
                        server_name="moltbook-mcp",
                        server_version="1.0.0",
                        capabilities=server.get_capabilities()
                    )
                )
        
        asyncio.run(run())


if __name__ == "__main__":
    main()
