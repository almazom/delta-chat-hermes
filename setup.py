"""Delta Chat account setup helper.

Provides interactive account creation with relay server discovery.
"""

import argparse
import re
import time
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
        List of bare relay domain names (e.g. "nine.testrun.org")
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
            # Filter out non-relay domains; dedup as we go
            if (
                domain
                and domain not in servers
                and not domain.startswith("chatmail.at")
                and not domain.startswith("assets")
                and not domain.startswith("og-preview")
            ):
                servers.append(domain)  # bare domain for dcaccount: URIs

        return servers if servers else [FALLBACK_RELAY]

    except Exception:
        # Return just the fallback on any error
        return [FALLBACK_RELAY]


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
        return self.rpc.get_all_accounts()

    def interactive_setup(self, profile_name: str = "default") -> Optional[str]:
        """Interactive account setup.

        Always uses first account. Creates one if none exists.
        Then checks if configured and sets up transport if needed.

        Args:
            profile_name: Hermes profile name for default account name suggestion

        Returns:
            Account ID of first account
        """
        print("=" * 60)
        print("Delta Chat Account Setup")
        print("=" * 60)

        # Get or create first account
        accounts = self.list_accounts()

        if not accounts:
            # Create new account
            print("\nNo Delta Chat account found, creating one...")
            default_name = profile_name if profile_name != "default" else "Hermes Bot"
            name = input(f"\nDisplay name [{default_name}]: ").strip()
            if not name:
                name = default_name

            account_id = self.rpc.add_account()
            self.rpc.set_config(account_id, "displayname", name)
            print(f"Account created! ID: {account_id}")
        else:
            account_id = accounts[0]["id"]
            print(f"\nUsing existing account: {account_id}")

        # Check if transport is configured
        if not self.rpc.is_configured(account_id):
            print("\nTransport not configured, setting up...")

            # Ask for account type
            while True:
                print("\nCreate account using:")
                print("-" * 40)
                print("1. Public relay (recommended - no personal info needed)")
                print("2. Existing email credentials")

                account_type = input("\nSelect option [1/2, default=1]: ").strip()

                if not account_type or account_type == "1":
                    # Public relay
                    servers = get_relay_servers()

                    # Strip https:// for display
                    display_servers = [s.replace("https://", "") for s in servers]

                    print("\nSelect relay server:")
                    print("-" * 40)
                    print(f"  1. {display_servers[0]} (default)")
                    for i, server in enumerate(display_servers[1:], 2):
                        print(f"  {i}. {server}")
                    print(f"  {len(servers) + 1}. Enter custom relay server")

                    relay_choice = input(f"\nSelect relay [1-{len(servers) + 1}, default=1]: ").strip()

                    if not relay_choice or relay_choice == "1":
                        relay = servers[0]
                    else:
                        try:
                            idx = int(relay_choice) - 1
                            if 0 <= idx < len(servers):
                                relay = servers[idx]
                            elif idx == len(servers):
                                relay = input("Enter relay server: ").strip()
                                # Add https:// if user didn't include it
                                if not relay.startswith("https://"):
                                    relay = f"https://{relay}"
                            else:
                                print(f"Invalid choice, using default: {display_servers[0]}")
                                relay = servers[0]
                        except ValueError:
                            print(f"Invalid choice, using default: {display_servers[0]}")
                            relay = servers[0]

                    # Strip https:// for QR code
                    relay_host = relay.replace("https://", "")
                    self.rpc.add_transport_from_qr(account_id, f"dcaccount:{relay_host}")
                    print(f"Transport configured using relay: {relay_host}")
                    break

                elif account_type == "2":
                    # Email credentials
                    email = input("\nEmail: ").strip()
                    password = input("Password: ").strip()

                    self.rpc.add_or_update_transport(account_id, {"addr": email, "password": password})
                    print(f"Transport configured using email: {email}")
                    break

                else:
                    print("Invalid choice, please try again.")

        # Offer to change display name
        current_name = self.rpc.get_account_info(account_id).get("name", "Unnamed")
        change_name = input(f"\nCurrent display name: '{current_name}'. Change? [y/N]: ").strip().lower()
        if change_name == "y":
            new_name = input(f"New display name [{current_name}]: ").strip()
            if new_name and new_name != current_name:
                try:
                    self.rpc.set_config(account_id, "displayname", new_name)
                    print(f"Name changed to: {new_name}")
                except Exception as e:
                    print(f"Failed to change name: {e}")

        return account_id

    def non_interactive_setup(
        self,
        profile_name: str = "default",
        name: Optional[str] = None,
        relay: Optional[str] = None,
        email: Optional[str] = None,
        password: Optional[str] = None,
    ) -> Optional[str]:
        """Create or reuse an account without prompting.

        Args:
            profile_name: Hermes profile name for default account name
            name: Display name for the bot
            relay: Public relay domain (e.g. nine.testrun.org)
            email: Existing email address
            password: Password for existing email

        Returns:
            Account ID or None if failed
        """
        accounts = self.list_accounts()
        if not accounts:
            default_name = name or (profile_name if profile_name != "default" else "Hermes Bot")
            account_id = self.rpc.add_account()
            self.rpc.set_config(account_id, "displayname", default_name)
            print(f"Account created! ID: {account_id}")
        else:
            account_id = accounts[0]["id"]
            print(f"Using existing account: {account_id}")

        if not self.rpc.is_configured(account_id):
            if email and password:
                self.rpc.add_or_update_transport(account_id, {"addr": email, "password": password})
                print(f"Transport configured using email: {email}")
            else:
                relay_host = (relay or get_relay_servers()[0]).replace("https://", "")
                self.rpc.add_transport_from_qr(account_id, f"dcaccount:{relay_host}")
                print(f"Transport configured using relay: {relay_host}")

        return account_id


def setup_account(rpc, profile_name: str = "default") -> Optional[str]:
    """Convenience function for account setup.

    Args:
        rpc: RPC instance
        profile_name: Hermes profile name for default account name

    Returns:
        Account ID or None if failed
    """
    try:
        setup = DeltaChatAccountSetup(rpc)
        return setup.interactive_setup(profile_name)
    except Exception as e:
        print(f"Setup failed: {e}")
        return None


def get_profiles():
    """Get list of Hermes profile directories."""
    import os

    default_profile = os.path.expanduser("~/.hermes")
    profiles_dir = os.path.join(os.path.expanduser("~/.hermes"), "profiles")
    profiles = []

    if os.path.exists(default_profile):
        profiles.append(("default", default_profile))

    if os.path.exists(profiles_dir):
        for name in sorted(os.listdir(profiles_dir)):
            profile_path = os.path.join(profiles_dir, name)
            if os.path.isdir(profile_path):
                profiles.append((name, profile_path))

    return profiles


def select_profile():
    """Interactive profile selection.

    Returns:
        Tuple of (profile_name, profile_path)
    """
    import os

    profiles = get_profiles()

    if not profiles:
        return ("default", os.path.expanduser("~/.hermes"))

    print("\nSelect Hermes Profile:")
    print("-" * 40)
    for i, (name, path) in enumerate(profiles, 1):
        print(f"  {i}. {name} ({path})")

    choice = input(f"\nSelect profile [1-{len(profiles)}, default=1]: ").strip()

    if not choice:
        return profiles[0]

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(profiles):
            return profiles[idx]
    except ValueError:
        pass

    print(f"Invalid choice, using default: {profiles[0][1]}")
    return profiles[0]


def get_account_address(rpc, account_id: int) -> Optional[str]:
    """Get the Delta Chat account address or SecureJoin link.

    Args:
        rpc: RPC instance
        account_id: The account ID

    Returns:
        SecureJoin link or account address (e.g., mybot@nine.testrun.org)
    """
    try:
        # Try to get SecureJoin QR code content (which is the link)
        try:
            qr_content = rpc.get_chat_securejoin_qr_code(account_id, None)  # chat_id - None for account-level QR
            if qr_content:
                return qr_content
        except Exception:
            pass

        # Fallback: get account info which should include address
        info = rpc.get_account_info(account_id)
        if info:
            # Try different field names for address
            address = info.get("address") or info.get("addr")
            if address:
                return address
            # Fallback: construct from name and server
            name = info.get("name", info.get("display_name", ""))
            server = info.get("server", "")
            if name and server:
                return f"{name}@{server}"
    except Exception:
        pass
    return None


def _wait_for_rpc(rpc, timeout: float = 10.0) -> bool:
    """Poll RPC server readiness with a short backoff."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            rpc.get_all_accounts()
            return True
        except Exception:
            time.sleep(0.5)
    return False


def _build_argparser():
    parser = argparse.ArgumentParser(description="Delta Chat account setup for Hermes")
    parser.add_argument("--non-interactive", action="store_true", help="Run without prompts")
    parser.add_argument("--relay", default=None, help="Public relay domain, e.g. nine.testrun.org")
    parser.add_argument("--email", default=None, help="Email address for existing credentials")
    parser.add_argument("--password", default=None, help="Password for existing email")
    parser.add_argument("--name", default=None, help="Display name for the bot")
    parser.add_argument("--profile", default=None, help="Hermes profile name")
    return parser


if __name__ == "__main__":
    import sys
    import os

    args = _build_argparser().parse_args()

    # Try to import deltachat2 from vendor or system
    import sys as _sys

    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    vendor_dir = os.path.join(plugin_dir, "vendor")
    if os.path.exists(vendor_dir) and vendor_dir not in _sys.path:
        _sys.path.insert(0, vendor_dir)

    try:
        import deltachat2
        from deltachat2.transport import IOTransport
    except ImportError as e:
        print(f"Error: {e}. Make sure the vendored directory is accessible.")
        sys.exit(1)

    # Enable debug logging for RPC if requested
    import logging

    if os.getenv("DELTACHAT_DEBUG"):
        logging.getLogger("deltachat2").setLevel(logging.DEBUG)
        logging.getLogger("deltachat2.IOTransport").setLevel(logging.DEBUG)
        logging.basicConfig(level=logging.DEBUG)

    # Select profile
    if args.non_interactive and args.profile:
        profile_name = args.profile
        hermes_home = os.path.join(os.path.expanduser("~/.hermes"), "profiles", args.profile)
        if not os.path.isdir(hermes_home):
            hermes_home = os.path.expanduser("~/.hermes")
    else:
        profile_name, hermes_home = select_profile()

    # Set accounts directory
    dc_accounts_path = os.path.join(hermes_home, "deltachat-platform")
    os.makedirs(dc_accounts_path, exist_ok=True)
    os.environ["DC_ACCOUNTS_PATH"] = dc_accounts_path
    os.environ["HERMES_HOME"] = hermes_home

    print(f"\nUsing profile: {hermes_home}")
    print(f"Account directory: {dc_accounts_path}")

    # Get RPC server path
    rpc_server = os.getenv("DELTACHAT_RPC_SERVER", "deltachat-rpc-server")

    # Initialize transport and RPC
    transport = IOTransport(accounts_dir=dc_accounts_path, rpc_server=rpc_server)
    transport.start()
    rpc = deltachat2.Rpc(transport)

    # Wait for RPC server to be ready
    if not _wait_for_rpc(rpc):
        print("Error: RPC server failed to start")
        transport.close()
        sys.exit(1)

    setup = DeltaChatAccountSetup(rpc)
    if args.non_interactive:
        account_id = setup.non_interactive_setup(
            profile_name=profile_name,
            name=args.name,
            relay=args.relay,
            email=args.email,
            password=args.password,
        )
    else:
        account_id = setup.interactive_setup(profile_name)

    # Display SecureJoin link if account was created
    if account_id:
        addr = get_account_address(rpc, account_id)
        if addr:
            print(f"\nSecureJoin link: {addr}")
            print("Share this link to chat with the bot via Delta Chat")

    transport.close()
