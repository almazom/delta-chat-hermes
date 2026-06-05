"""Delta Chat account setup helper.

Provides interactive account creation with relay server discovery.
"""

import re
import urllib.request
from typing import List, Optional

# Default fallback relay (only used if scraping fails)
FALLBACK_RELAY = "nine.testrun.org"
RELAY_SERVERS_URL = "https://chatmail.at/relays"


def scrape_relay_servers(timeout: int = 10) -> List[str]:
    """Scrape relay servers from chatmail.at/relays.

    Args:
        timeout: HTTP request timeout in seconds

    Returns:
        List of relay server addresses (with https:// prefix)
    """
    servers = []

    try:
        with urllib.request.urlopen(RELAY_SERVERS_URL, timeout=timeout) as resp:
            text = resp.read().decode("utf-8")

        # Find relay server URLs in href attributes - they look like
        # <a href="https://nine.testrun.org" class="hilite">nine.testrun.org</a>
        # or <a href="https://mehl.cloud">mehl.cloud</a>
        server_pattern = r'href="(https://[a-zA-Z0-9\-\.]+)"'

        matches = re.findall(server_pattern, text)
        for server in matches:
            # Extract just the domain (remove https://)
            domain = server.replace("https://", "")
            # Filter out non-relay domains
            if (
                domain
                and domain not in servers
                and not domain.startswith("chatmail.at")
                and not domain.startswith("assets")
                and not domain.startswith("og-preview")
            ):
                servers.append(server)  # Keep full URL

        # Deduplicate while preserving order
        seen = set()
        unique_servers = []
        for s in servers:
            if s not in seen:
                seen.add(s)
                unique_servers.append(s)

        # If we found servers, return them. Otherwise return fallback.
        return unique_servers if unique_servers else [f"https://{FALLBACK_RELAY}"]

    except Exception:
        # Return just the fallback on any error
        return [f"https://{FALLBACK_RELAY}"]


def get_relay_servers() -> List[str]:
    """Get list of available relay servers.

    Returns:
        List of relay server addresses
    """
    return scrape_relay_servers()


class DeltaChatAccountSetup:
    """Helper for setting up Delta Chat accounts."""

    def __init__(self, rpc):
        """Initialize with RPC client.

        Args:
            rpc: DeltaChat2 RPC instance
        """
        self.rpc = rpc

    def list_accounts(self) -> List[dict]:
        """List all configured Delta Chat accounts.

        Returns:
            List of account dictionaries
        """
        return self.rpc.call("get_all_accounts")

    def create_account_on_relay(
        self, name: str, relay_server: Optional[str] = None
    ) -> Optional[str]:
        """Create account on a public relay.

        Args:
            name: Display name for the account
            relay_server: Relay server to use (defaults to first available)

        Returns:
            Account ID or None if failed
        """
        try:
            if relay_server is None:
                servers = get_relay_servers()
                relay_server = servers[0] if servers else FALLBACK_RELAY

            # Create account on relay without personal info
            account_id = self.rpc.call(
                "add_account",
                {
                    "name": name,
                    "server": relay_server,
                },
            )
            return account_id
        except Exception as e:
            print(f"Error creating relay account: {e}")
            return None

    def create_account_manual(self, email: str, password: str) -> Optional[str]:
        """Create account with email credentials.

        Args:
            email: Email address
            password: Password

        Returns:
            Account ID or None if failed
        """
        try:
            account_id = self.rpc.call(
                "add_account",
                {
                    "email": email,
                    "password": password,
                },
            )
            return account_id
        except Exception as e:
            print(f"Error creating manual account: {e}")
            return None

    def interactive_setup(self) -> str:
        """Interactive account setup.

        Returns:
            Account ID of created/selected account
        """
        print("=" * 60)
        print("Delta Chat Account Setup")
        print("=" * 60)

        # Check existing accounts
        accounts = self.list_accounts()
        if accounts:
            print(f"\nFound {len(accounts)} existing account(s):")
            for i, acc in enumerate(accounts):
                print(
                    f"  {i+1}. {acc.get('name', 'Unnamed')} (ID: {acc['account_id']})"
                )

            choice = input("\nUse existing account? [y/N]: ").strip().lower()
            if choice == "y":
                idx = int(input("Select account number: ").strip()) - 1
                if 0 <= idx < len(accounts):
                    return accounts[idx]["account_id"]

        # Create new account
        print("\nCreate New Account")
        print("-" * 40)
        print("1. Create on public relay (no personal info, just a name)")
        print("2. Manual email credentials")

        choice = input("\nSelect option [1/2]: ").strip()

        if choice == "1":
            name = input("Display name: ").strip()
            if not name:
                name = "Hermes Bot"

            servers = get_relay_servers()

            use_default = input("\nUse default relay? [Y/n]: ").strip().lower()
            if use_default != "n":
                relay = servers[0]
            else:
                relay = input(f"Enter relay server [{servers[0]}]: ").strip()
                relay = relay or servers[0]

            print(f"\nCreating account '{name}' on relay: {relay}")
            account_id = self.create_account_on_relay(name, relay)
            print(f"Account created! ID: {account_id}")
            return account_id

        elif choice == "2":
            email = input("Email: ").strip()
            password = input("Password: ").strip()
            account_id = self.create_account_manual(email, password)
            if account_id:
                print(f"Account created! ID: {account_id}")
                return account_id
            else:
                print("Failed to create account")
                return None
        else:
            print("Invalid choice")
            # Don't recurse infinitely - return None after invalid input
            return None


def setup_account(rpc) -> Optional[str]:
    """Convenience function for account setup.

    Args:
        rpc: RPC instance

    Returns:
        Account ID or None if failed
    """
    try:
        setup = DeltaChatAccountSetup(rpc)
        return setup.interactive_setup()
    except Exception as e:
        print(f"Setup failed: {e}")
        return None
