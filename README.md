# Delta Chat Platform Plugin for Hermes Agent

A Hermes platform plugin that integrates Delta Chat as a messaging channel.
Uses **deltachat2** for direct JSON-RPC access (not abstracted away).

## Quick Start

```bash
# Install deltachat-rpc-server binary
pip install deltachat-rpc-server

# Clone plugin to Hermes
git clone https://github.com/Simon-Laux/deltachat-hermes ~/.hermes/plugins/deltachat

# Enable plugin
hermes plugins enable deltachat

# Start gateway
hermes gateway start
```

## Installation

### 1. Install deltachat-rpc-server

**Option A: pip (recommended for most systems)**
```bash
pip install deltachat-rpc-server
```

**Option B: From source**
```bash
git clone https://github.com/chatmail/core
cd core
cargo build -p deltachat-rpc-server --release
# Binary: target/release/deltachat-rpc-server
```

**Option C: NixOS**
```bash
nix profile install nixpkgs#deltachat-rpc-server
```

### 2. (Optional) Configure RPC server path

If binary is not in PATH:
```bash
# For default profile
echo 'DELTACHAT_RPC_SERVER=/path/to/deltachat-rpc-server' >> ~/.hermes/.env

# For named profile
hermes -p my-profile config set env.DELTACHAT_RPC_SERVER /path/to/deltachat-rpc-server
```

### 3. Enable Plugin

```bash
hermes plugins enable deltachat
```

## Usage

### Basic Usage

```bash
# Start gateway (automatically connects to first DC account)
hermes gateway start
```

The plugin will:
1. Set `DC_ACCOUNTS_PATH` to `<profile>/deltachat/`
2. Start `deltachat-rpc-server` automatically
3. Check version compatibility (blocks older than 2.51.0, warns on newer)
4. Use first Delta Chat account found
5. Begin forwarding messages bidirectionally

### First Run: Account Setup

On first run, the plugin will guide you through account creation:

```
Delta Chat Account Setup
========================

Create New Account
----------------------------------------
1. Create on public relay (no personal info, just a name)
2. Manual email credentials

Select option [1/2]: 1
Display name: My Bot

Use default relay? [Y/n]: Y

Creating account 'My Bot' on relay: nine.testrun.org
Account created! ID: 12345
```

The setup offers to create an account on a public relay without requiring
personal information - you only need to provide a display name. You can choose
from a list of available relay servers scraped from chatmail.at, or use
the default (nine.testrun.org).

### Multiple Agents

Each Hermes profile = one Delta Chat account:

```bash
# Create profiles
hermes profile create work
hermes profile create personal

# Each gets its own DC config at:
# ~/.hermes/profiles/work/deltachat/
# ~/.hermes/profiles/personal/deltachat/

# Start gateways
work gateway start
personal gateway start
```

## Features

### Phase 1: Messaging Adapter
- Bidirectional text messaging via direct JSON-RPC
- Multi-agent support via Hermes profiles
- Automatic account selection (first available)
- Chat metadata (name, type, user info)
- Version guard: blocks older than 2.51.0, warns on newer

### Phase 2: Webxdc Support
- Send .xdc files via `send_file()` RPC call
- Bundled `webxdc-converter` skill
- Access via `skill_view("deltachat:webxdc-converter")`

### Phase 3: Voice Messages (Planned)
- Audio attachment detection
- Automatic transcription via Hermes STT
- Forward transcription as text to AI

### Phase 4: Voice Calls (Planned)
- Incoming call detection via `IncomingCall` event
- WebRTC bridge via aiortc
- Uses `iceServers()` and `acceptIncomingCall()` RPC methods
- Real-time audio processing

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DELTACHAT_RPC_SERVER` | No | `deltachat-rpc-server` | Path to RPC binary |
| `DELTACHAT_HOME_CHANNEL` | No | - | Default chat for cron delivery |

## Documentation

- [Version Compatibility](docs/version-compatibility.md) - Version requirements
- [File Structure](docs/file-structure.md) - Directory layout
- [Troubleshooting](docs/troubleshooting.md) - Common issues

## Development

### Vendored Dependencies

The `deltachat2` Python package is vendored in the `vendor/` directory for simplified
installation. This avoids requiring users to manually install the package.

**Note:** If you need to update the vendored `deltachat2` package:
1. Fetch the latest version from [adbenitez/deltachat2](https://github.com/adbenitez/deltachat2)
2. Copy the `deltachat2/` directory contents to `vendor/deltachat2/`
3. Test thoroughly as API changes may affect compatibility
4. Update the minimum version in `adapter.py` if needed

## License

Mozilla Public License 2.0 (MPL-2.0)

---

## References

- [Hermes Agent](https://github.com/NousResearch/hermes-agent)
- [Hermes Profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles)
- [Delta Chat](https://delta.chat/)
- [deltachat2 PyPI](https://pypi.org/project/deltachat2/)
- [deltachat-rpc-server](https://github.com/chatmail/core/tree/main/deltachat-rpc-server)
- [Delta Chat JSON-RPC API](https://github.com/chatmail/core/blob/main/deltachat-jsonrpc/src/api.rs)
- [Delta Chat Core](https://github.com/chatmail/core)
- [Webxdc](https://webxdc.org/)
- [aiortc](https://aiortc.readthedocs.io/)
