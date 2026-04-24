#!/usr/bin/env python3
"""
x402 Payment Verifier for MCP Server
Handles real x402 payment verification via Coinbase CDP facilitator.
"""

import json
import os
import requests
from typing import Optional, Dict, Any
from dataclasses import dataclass

# x402 Configuration
X402_FACILITATOR_URL = os.environ.get("X402_FACILITATOR_URL", "https://x402.coinbase.com")
X402_NETWORK = os.environ.get("X402_NETWORK", "base-mainnet")  # or "base-sepolia" for testnet
X402_RECIPIENT_ADDRESS = os.environ.get("X402_RECIPIENT_ADDRESS", "")  # Your wallet address


@dataclass
class X402PaymentRequest:
    """x402 payment request structure"""
    amount: str  # Amount in smallest unit (wei for ETH/USDC)
    token_address: str  # USDC contract address
    chain_id: str  # CAIP-2 chain ID (eip155:8453 for Base mainnet)
    recipient: str  # Your wallet address
    
    
@dataclass
class X402PaymentResult:
    """Result of payment verification"""
    success: bool
    transaction_hash: Optional[str]
    error_message: Optional[str]
    amount_paid: float


class X402Verifier:
    """
    Verifies x402 payments using Coinbase CDP facilitator.
    
    Flow:
    1. Server returns 402 with PAYMENT-REQUIRED header (JSON with price, token, network)
    2. Client constructs payment via x402 client SDK
    3. Client sends PAYMENT-SIGNATURE header with signed transaction
    4. Server verifies via facilitator API
    """
    
    # USDC on Base mainnet
    USDC_BASE_MAINNET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
    
    # Chain IDs (CAIP-2 format)
    CHAIN_BASE_MAINNET = "eip155:8453"
    CHAIN_BASE_SEPOLIA = "eip155:84532"
    
    def __init__(self, 
                 recipient_address: Optional[str] = None,
                 network: str = "base-mainnet",
                 facilitator_url: Optional[str] = None):
        """
        Initialize x402 verifier.
        
        Args:
            recipient_address: Your wallet address to receive payments
            network: "base-mainnet" or "base-sepolia"
            facilitator_url: Optional custom facilitator URL
        """
        self.recipient_address = recipient_address or X402_RECIPIENT_ADDRESS
        self.network = network
        self.facilitator_url = facilitator_url or X402_FACILITATOR_URL
        
        # Set token and chain based on network
        if network == "base-mainnet":
            self.token_address = self.USDC_BASE_MAINNET
            self.chain_id = self.CHAIN_BASE_MAINNET
        else:
            self.token_address = self.USDC_BASE_SEPOLIA
            self.chain_id = self.CHAIN_BASE_SEPOLIA
        
        if not self.recipient_address:
            print("[x402] WARNING: No recipient address set. Payments will fail.")
    
    def create_payment_requirement(self, amount_usd: float) -> Dict[str, Any]:
        """
        Create a payment requirement for the client.
        This is what the server sends in the 402 response.
        
        Args:
            amount_usd: Amount in USD (e.g., 0.05 for $0.05)
            
        Returns:
            Payment requirement dict for PAYMENT-REQUIRED header
        """
        # Convert USD to USDC (6 decimals)
        amount_wei = int(amount_usd * 1_000_000)  # USDC has 6 decimals
        
        return {
            "scheme": "x402",
            "networkId": self.chain_id,
            "requiredFee": {
                "amount": str(amount_wei),
                "tokenAddress": self.token_address,
                "tokenDecimals": 6,
                "tokenSymbol": "USDC"
            },
            "recipient": self.recipient_address,
            "description": f"Payment for Moltbook MCP tool",
            "facilitator": self.facilitator_url
        }
    
    def verify_payment(self, payment_signature: str, expected_amount: float) -> X402PaymentResult:
        """
        Verify a payment signature from the client.
        
        Args:
            payment_signature: The PAYMENT-SIGNATURE header value (JSON string)
            expected_amount: Expected amount in USD
            
        Returns:
            X402PaymentResult with success status and details
        """
        if not payment_signature:
            return X402PaymentResult(
                success=False,
                transaction_hash=None,
                error_message="No payment signature provided",
                amount_paid=0.0
            )
        
        try:
            # Parse the payment signature
            payment_data = json.loads(payment_signature)
            
            # Verify via facilitator API
            verify_url = f"{self.facilitator_url}/verify"
            
            response = requests.post(
                verify_url,
                json={
                    "payment": payment_data,
                    "expectedAmount": str(int(expected_amount * 1_000_000)),
                    "tokenAddress": self.token_address,
                    "recipient": self.recipient_address,
                    "networkId": self.chain_id
                },
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get("valid"):
                    return X402PaymentResult(
                        success=True,
                        transaction_hash=result.get("transactionHash"),
                        error_message=None,
                        amount_paid=expected_amount
                    )
                else:
                    return X402PaymentResult(
                        success=False,
                        transaction_hash=None,
                        error_message=result.get("error", "Payment verification failed"),
                        amount_paid=0.0
                    )
            else:
                return X402PaymentResult(
                    success=False,
                    transaction_hash=None,
                    error_message=f"Facilitator error: {response.status_code}",
                    amount_paid=0.0
                )
                
        except json.JSONDecodeError as e:
            return X402PaymentResult(
                success=False,
                transaction_hash=None,
                error_message=f"Invalid payment signature format: {e}",
                amount_paid=0.0
            )
        except requests.RequestException as e:
            return X402PaymentResult(
                success=False,
                transaction_hash=None,
                error_message=f"Network error: {e}",
                amount_paid=0.0
            )
        except Exception as e:
            return X402PaymentResult(
                success=False,
                transaction_hash=None,
                error_message=f"Verification error: {e}",
                amount_paid=0.0
            )
    
    def check_payment_status(self, transaction_hash: str) -> bool:
        """
        Check if a payment transaction is confirmed on-chain.
        
        Args:
            transaction_hash: The transaction hash to check
            
        Returns:
            True if confirmed, False otherwise
        """
        try:
            status_url = f"{self.facilitator_url}/status/{transaction_hash}"
            response = requests.get(status_url, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                return result.get("status") == "confirmed"
            
            return False
        except:
            return False


class X402PaymentHandler:
    """
    Enhanced payment handler with real x402 verification.
    Falls back to placeholder mode if x402 not configured.
    """
    
    PRICING = {
        "moltbook_post": 0.05,      # $0.05 per post
        "moltbook_comment": 0.02,   # $0.02 per comment
        "moltbook_upvote": 0.01,    # $0.01 per upvote
        "moltbook_solve_captcha": 0.00,  # Free (attracts users)
        "get_pricing": 0.00,        # Free
        "get_stats": 0.00,          # Free
    }
    
    def __init__(self):
        self.payments_received = {}
        self.total_revenue_usd = 0.0
        
        # Initialize x402 verifier if configured
        recipient = os.environ.get("X402_RECIPIENT_ADDRESS")
        if recipient:
            self.verifier = X402Verifier(recipient_address=recipient)
            self.x402_enabled = True
            print(f"[x402] Payment verification ENABLED for {recipient}")
        else:
            self.verifier = None
            self.x402_enabled = False
            print("[x402] Payment verification DISABLED (no X402_RECIPIENT_ADDRESS)")
    
    def get_price(self, tool_name: str) -> float:
        return self.PRICING.get(tool_name, 0.01)
    
    def is_free_tool(self, tool_name: str) -> bool:
        return self.get_price(tool_name) == 0
    
    def check_payment(self, tool_name: str, payment_token: Optional[str] = None) -> tuple[bool, Optional[str]]:
        """
        Check if payment is valid for a tool.
        
        Args:
            tool_name: Name of the tool being called
            payment_token: x402 payment signature from client
            
        Returns:
            (success: bool, error_message: Optional[str])
        """
        # Free tools don't need payment
        if self.is_free_tool(tool_name):
            return True, None
        
        # If no verifier configured, accept any token (placeholder mode)
        if not self.x402_enabled:
            if payment_token:
                # Log the "payment" for stats
                self.payments_received[tool_name] = self.payments_received.get(tool_name, 0) + 1
                self.total_revenue_usd += self.get_price(tool_name)
                return True, None
            else:
                return False, f"Payment required: ${self.get_price(tool_name)}. Set X402_RECIPIENT_ADDRESS to enable real verification."
        
        # Real x402 verification
        if not payment_token:
            return False, f"Payment required: ${self.get_price(tool_name)} USDC on Base"
        
        # Verify the payment
        expected_amount = self.get_price(tool_name)
        result = self.verifier.verify_payment(payment_token, expected_amount)
        
        if result.success:
            self.payments_received[tool_name] = self.payments_received.get(tool_name, 0) + 1
            self.total_revenue_usd += result.amount_paid
            return True, None
        else:
            return False, result.error_message
    
    def get_payment_requirement(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the payment requirement for a tool (for 402 response).
        
        Returns:
            Payment requirement dict or None if free tool
        """
        if self.is_free_tool(tool_name):
            return None
        
        if not self.x402_enabled:
            return {
                "scheme": "x402",
                "status": "placeholder",
                "amount": self.get_price(tool_name),
                "currency": "USDC",
                "message": "Set X402_RECIPIENT_ADDRESS environment variable to enable real payments"
            }
        
        return self.verifier.create_payment_requirement(self.get_price(tool_name))
    
    def get_stats(self) -> dict:
        return {
            "payments_received": self.payments_received,
            "total_revenue_usd": round(self.total_revenue_usd, 4),
            "total_tools": len(self.PRICING),
            "free_tools": sum(1 for p in self.PRICING.values() if p == 0),
            "paid_tools": sum(1 for p in self.PRICING.values() if p > 0),
            "x402_enabled": self.x402_enabled,
            "recipient_address": self.verifier.recipient_address if self.verifier else None,
        }


if __name__ == "__main__":
    # Test the verifier
    print("Testing x402 Verifier...")
    
    # Test without recipient
    handler = X402PaymentHandler()
    print(f"Stats (no recipient): {json.dumps(handler.get_stats(), indent=2)}")
    
    # Test payment check
    success, error = handler.check_payment("moltbook_post")
    print(f"Payment check (no token): success={success}, error={error}")
    
    success, error = handler.check_payment("moltbook_post", "dummy_token")
    print(f"Payment check (with token): success={success}, error={error}")
    
    print(f"\nFinal stats: {json.dumps(handler.get_stats(), indent=2)}")
