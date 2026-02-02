# AWS API MCP (Andes) Connection Fix

## Problem
You're seeing: `MCP error -32000: Connection closed` for andes-mcp (aws-api-mcp)

## Current Configuration Status ✅
Your configuration is **correct**:
```json
{
  "aws-api-mcp": {
    "command": "/home/nflos/.toolbox/bin/mcp-registry",
    "args": ["start-server", "aws-api-mcp"],
    "disabled": false
  }
}
```

## Issue
The server is configured correctly but may be timing out on startup. The "Connection closed" error typically means the MCP server process started but closed immediately.

## Solution

### Step 1: Add Timeout to Configuration

Update your MCP settings to include a longer timeout:

```bash
cat > ~/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json <<'EOF'
{
  "mcpServers": {
    "builder-mcp": {
      "command": "/home/nflos/.toolbox/bin/builder-mcp",
      "args": [],
      "disabled": false,
      "timeout": 60
    },
    "aws-api-mcp": {
      "command": "/home/nflos/.toolbox/bin/mcp-registry",
      "args": ["start-server", "aws-api-mcp"],
      "disabled": false,
      "timeout": 60
    }
  }
}
EOF
```

### Step 2: Restart VS Code Completely

**Critical:** You MUST fully restart VS Code (not just reload window):
1. Close VS Code completely
2. Wait a few seconds
3. Reopen VS Code

### Step 3: Verify

After restarting:
1. Open Cline settings (gear icon ⚙️)
2. Check "MCP Servers" section
3. Both servers should show green indicators

## If It Still Doesn't Work

### Check Cline Output Logs

1. Open Output panel: View → Output
2. Select "Cline" from dropdown
3. Look for specific error messages about aws-api-mcp

### Test mcp-registry Manually

Try running it directly to see detailed errors:
```bash
/home/nflos/.toolbox/bin/mcp-registry start-server aws-api-mcp
```

If you see errors, they might indicate:
- Missing Java dependencies
- Configuration issues with the server
- Permission problems

### Alternative: Use Wrapper Script

If mcp-registry still fails, try using the wrapper script directly:

```json
{
  "aws-api-mcp": {
    "command": "/home/nflos/.config/smithy-mcp/mcp-servers/aws-api-mcp",
    "args": [],
    "disabled": false,
    "timeout": 60
  }
}
```

This wrapper script calls mcp-registry internally but may handle some environment issues better.

## Comparison with Working Desktop

If your other cloud desktop has it working, check its configuration:

```bash
# On the working desktop, run:
cat ~/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json

# Or if using VS Code Server:
cat ~/.vscode-server/data/User/globalStorage/asbx.amzn-cline/settings/cline_mcp_settings.json
```

Compare the working configuration with this one and note any differences.

## Desktop Directory Issue (Already Fixed)

✅ Desktop directory exists and is not the issue
- Location: `/home/nflos/Desktop`
- This was a potential cause but has been verified to exist

## Quick Fix Summary

1. **Add timeout: 60** to both MCP servers in config
2. **Fully restart VS Code** (close and reopen)
3. **Check Cline logs** if still failing
4. **Try wrapper script** as alternative if needed

The most likely fix is adding the timeout parameter and doing a full VS Code restart.
