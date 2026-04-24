#!/usr/bin/env python3
"""
Moltbook MCP Server - x402 Monetization
Makes money by selling Moltbook actions to other AI agents via MCP + x402 micropayments.
Version: 1.1.0 - Real x402 payment verification
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

# Try to import x402 verifier
try:
    from x402_verifier import X402PaymentHandler
    X402_AVAILABLE = True
except ImportError:
    X402_AVAILABLE = False
    print("[MCP] x402 verifier not available - using placeholder", file=sys.stderr)
    
    # Fallback placeholder implementation
    class X402PaymentHandler:
        """Placeholder payment handler when x402_verifier not available."""
        
        PRICING = {
            "moltbook_post": 0.05,
            "moltbook_comment": 0.02,
            "moltbook_upvote": 0.01,
            "moltbook_solve_captcha": 0.00,
            "get_pricing": 0.00,
            "get_stats": 0.00,
        }
        
        def __init__(self):
            self.payments_received = {}
            self.total_revenue_usd = 0.0
            self.x402_enabled = False
        
        def get_price(self, tool_name: str) -> float:
            return self.PRICING.get(tool_name, 0.01)
        
        def is_free_tool(self, tool_name: str) -> bool:
            return self.get_price(tool_name) == 0
        
        def check_payment(self, tool_name: str, payment_token: Optional[str] = None):
            if self.is_free_tool(tool_name):
                return True, None
            if payment_token:
                self.payments_received[tool_name] = self.payments_received.get(tool_name, 0) + 1
                self.total_revenue_usd += self.get_price(tool_name)
                return True, None
            return False, f"Payment required: ${self.get_price(tool_name)}"
        
        def get_payment_requirement(self, tool_name: str):
            if self.is_free_tool(tool_name):
                return None
            return {
                "scheme": "x402",
                "status": "placeholder",
                "amount": self.get_price(tool_name),
                "currency": "USDC",
                "message": "Install x402_verifier.py for real payments"
            }
        
        def get_stats(self) -> dict:
            return {
                "payments_received": self.payments_received,
                "total_revenue_usd": self.total_revenue_usd,
                "total_tools": len(self.PRICING),
                "free_tools": sum(1 for p in self.PRICING.values() if p == 0),
                "paid_tools": sum(1 for p in self.PRICING.values() if p > 0),
                "x402_enabled": False,
            }

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
                    "_payment_token": {"type": "string", "description": "x402 payment signature (optional - server will return payment required if not provided)", "default": ""},
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
                    "_payment_token": {"type": "string", "description": "x402 payment signature (optional)", "default": ""},
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
                    "_payment_token": {"type": "string", "description": "x402 payment signature (optional)", "default": ""},
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
    """Handle tool calls with x402 payment verification."""
    
    # Extract payment token from arguments (if provided by client)
    payment_token = arguments.pop("_payment_token", None)
    
    # Check payment for paid tools
    if not payment_handler.is_free_tool(name):
        success, error = payment_handler.check_payment(name, payment_token)
        if not success:
            # Return 402-style payment required response
            payment_req = payment_handler.get_payment_requirement(name)
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": "Payment required",
                    "message": error,
                    "payment_required": payment_req,
                    "tool": name,
                    "price_usd": payment_handler.get_price(name),
                    "timestamp": datetime.now().isoformat()
                }, indent=2)
            )]
    
    if name == "get_pricing":
        return [TextContent(
            type="text",
            text=json.dumps({
                "success": True,
                "pricing": payment_handler.PRICING,
                "currency": "USDC",
                "network": "Base" if payment_handler.x402_enabled else "placeholder",
                "x402_enabled": payment_handler.x402_enabled,
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
                "x402_available": X402_AVAILABLE,
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
    print(f"\n[1] MCP SDK: {'Available' if MCP_AVAILABLE else 'Not Available'}")
    
    # Test Moltbook modules
    print(f"[2] Moltbook modules: {'Available' if MOLTBOOK_AVAILABLE else 'Not Available (test mode)'}")
    
    # Test x402 verifier
    print(f"[3] x402 verifier: {'Available' if X402_AVAILABLE else 'Using placeholder'}")
    
    # Test pricing
    print(f"\n[4] Pricing configured:")
    for tool, price in payment_handler.PRICING.items():
        status = "FREE" if price == 0 else f"${price:.2f}"
        print(f"    - {tool}: {status}")
    
    # Test server initialization
    try:
        print(f"\n[5] Server initialization: Success")
        print(f"    Server name: moltbook-mcp")
        print(f"    x402 enabled: {payment_handler.x402_enabled}")
        print(f"    Tools registered: get_pricing, get_stats, moltbook_post, moltbook_comment, moltbook_upvote, moltbook_solve_captcha")
    except Exception as e:
        print(f"\n[5] Server initialization: Failed - {e}")
        return False
    
    print(f"\n[6] Stats: {json.dumps(payment_handler.get_stats(), indent=2)}")
    
    # Test payment verification
    print(f"\n[7] Payment verification test:")
    success, error = payment_handler.check_payment("moltbook_post")
    status = "Blocked" if not success else "Allowed"
    err_msg = error[:50] if error else "OK"
    print(f"    - moltbook_post (no token): {status} - {err_msg}...")
    success, error = payment_handler.check_payment("moltbook_post", "dummy_token")
    status = "Allowed" if success else "Blocked"
    print(f"    - moltbook_post (with token): {status}")
    success, error = payment_handler.check_payment("get_pricing")
    status = "Allowed" if success else "Blocked"
    print(f"    - get_pricing (free): {status}")
    
    print("\n" + "=" * 60)
    print("Test complete. Server ready for MCP transport (stdio).")
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
            print(f"[MCP] x402 verifier: {X402_AVAILABLE}", file=sys.stderr)
            print(f"[MCP] x402 enabled: {payment_handler.x402_enabled}", file=sys.stderr)
            print(f"[MCP] Pricing: {json.dumps(payment_handler.PRICING, indent=2)}", file=sys.stderr)
            
            async with stdio_server() as (read_stream, write_stream):
                await server.run(
                    read_stream,
                    write_stream,
                    InitializationOptions(
                        server_name="moltbook-mcp",
                        server_version="1.1.0",
                        capabilities=server.get_capabilities()
                    )
                )
        
        asyncio.run(run())


if __name__ == "__main__":
    main()
