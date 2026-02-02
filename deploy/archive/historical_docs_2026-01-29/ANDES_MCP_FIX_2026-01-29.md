# Andes MCP Fix - January 29, 2026

## Problem
Andes MCP server was failing with connection errors.

## Root Causes Found

### 1. Node.js Version Mismatch ⚠️
- **Required:** Node.js 20+
- **Installed:** Node.js 18.20.2
- **Error:** "Node version 18 detected, but version 20 or higher is required"

### 2. Incorrect MCP Configuration
- **Wrong:** Using `mcp-registry start-server andes-mcp`
- **Correct:** Call `/home/nflos/.toolbox/bin/andes-mcp` directly

## Fixes Applied

### Fix 1: Upgraded Node.js
```bash
# Updated ~/.config/mise/config.toml
node = "20.19.2"  # was: 18.20.2

# Activated new version
mise install node@20.19.2
mise use node@20.19.2
```

### Fix 2: Updated MCP Configuration
**File:** `~/.vscode-server/data/User/globalStorage/asbx.amzn-cline/settings/cline_mcp_settings.json`

**Changed from:**
```json
"andes-mcp": {
  "command": "/home/nflos/.toolbox/bin/mcp-registry",
  "args": ["start-server", "andes-mcp"]
}
```

**Changed to:**
```json
"andes-mcp": {
  "command": "/home/nflos/.toolbox/bin/andes-mcp",
  "args": []
}
```

## Next Steps

### 1. Restart VS Code
**CRITICAL:** You must fully restart VS Code (not just reload window):
1. Close VS Code completely
2. Wait a few seconds
3. Reopen VS Code

### 2. Verify MCP Connection
After restarting:
1. Open Cline settings (gear icon ⚙️)
2. Check "MCP Servers" section
3. `andes-mcp` should show green indicator

### 3. Test Andes MCP
Try a command that uses Andes:
```
Can you help me with [andes-specific task]?
```

## Backup Created
Original config backed up to:
```
~/.vscode-server/data/User/globalStorage/asbx.amzn-cline/settings/cline_mcp_settings.json.backup
```

## Why This Happened
The andes-mcp server was recently updated to require Node 20+, but your environment was still using Node 18. Additionally, calling through `mcp-registry` can cause Java stack traces that break the MCP protocol.

## Related Documentation
- `deploy/archive/mcp_setup/ANDES_MCP_FIX.md`
- `deploy/archive/mcp_setup/AMAZON_MCP_TROUBLESHOOTING.md`

## Status
✅ Node.js upgraded to 20.19.2
✅ MCP config updated to call binary directly
⏳ Awaiting VS Code restart for changes to take effect
