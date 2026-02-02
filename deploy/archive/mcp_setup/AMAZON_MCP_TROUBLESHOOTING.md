# Amazon MCP Server Troubleshooting Guide

## Critical Issue: Java Stack Traces Breaking MCP Connection

### Problem Description

When Amazon MCP servers are configured to run through `aim mcp start-server`, they print Java stack traces to stdout, which breaks the MCP protocol connection.

**Error Messages You'll See:**
```
Unexpected token 'j', "java.lang."... is not valid JSON
MCP error -32000: Connection closed
Failed to connect to MCP server
```

**Root Cause:**
- MCP protocol requires **only** JSON-RPC messages on stdout
- Running servers through `aim` causes Java logging/errors to be printed to stdout
- These non-JSON messages break the MCP client parser

### The Solution

**Call MCP server binaries DIRECTLY instead of through `aim`**

## Wrong vs Correct Configuration

### ❌ INCORRECT (causes Java errors):
```json
{
  "mcpServers": {
    "builder-mcp": {
      "command": "/home/nflos/.toolbox/bin/aim",
      "args": ["mcp", "start-server", "builder-mcp"],
      "disabled": false
    }
  }
}
```

### ✅ CORRECT (works properly):
```json
{
  "mcpServers": {
    "builder-mcp": {
      "command": "/home/nflos/.toolbox/bin/builder-mcp",
      "args": [],
      "disabled": false
    }
  }
}
```

## How to Fix

### Step 1: Locate Your Cline MCP Settings File

The file location varies by VS Code variant:

**Regular VS Code:**
```
~/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json
```

**VS Code Server (Cloud Desktop):**
```
~/.vscode-server/data/User/globalStorage/asbx.amzn-cline/settings/cline_mcp_settings.json
```

**Cursor:**
```
~/.config/Cursor/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json
```

### Step 2: Find Which Servers Need Fixing

Check your configuration file. Any server configured like this needs fixing:
```json
"command": "/home/nflos/.toolbox/bin/aim",
"args": ["mcp", "start-server", "server-name"]
```

### Step 3: Fix Each Server Configuration

For each broken server, change from:
- `"command": "/home/nflos/.toolbox/bin/aim"`
- `"args": ["mcp", "start-server", "<server-name>"]`

To:
- `"command": "/home/nflos/.toolbox/bin/<server-name>"`
- `"args": []`

### Step 4: Verify Server Binary Exists

Before fixing, verify the server binary exists:
```bash
ls -la /home/nflos/.toolbox/bin/<server-name>
```

## Common Amazon MCP Servers

### Servers That Need This Fix:

**builder-mcp** (Amazon internal tools):
```json
{
  "command": "/home/nflos/.toolbox/bin/builder-mcp",
  "args": [],
  "disabled": false,
  "timeout": 60
}
```

**agentz-mcp** (AgentZ tools):
```json
{
  "command": "/home/nflos/.toolbox/bin/agentz-mcp",
  "args": [],
  "disabled": false,
  "timeout": 60
}
```

**amazon-diag-mcp** (Diagnostics):
```json
{
  "command": "/home/nflos/.toolbox/bin/amazon-diag-mcp",
  "args": [],
  "disabled": false,
  "timeout": 60
}
```

### Servers That Are Already Correct:

These servers are typically already configured correctly (don't change them):
- `datanet-mcp`
- `aws-smithy-lambda-mcp`
- `diagram-tools-mcp`
- `aws-api-mcp`

## Complete Working Configuration Example

```json
{
  "mcpServers": {
    "builder-mcp": {
      "command": "/home/nflos/.toolbox/bin/builder-mcp",
      "args": [],
      "disabled": false,
      "timeout": 60
    },
    "agentz-mcp": {
      "command": "/home/nflos/.toolbox/bin/agentz-mcp",
      "args": [],
      "disabled": false,
      "timeout": 60
    },
    "amazon-diag-mcp": {
      "command": "/home/nflos/.toolbox/bin/amazon-diag-mcp",
      "args": [],
      "disabled": false,
      "timeout": 60
    },
    "datanet-mcp": {
      "command": "/home/nflos/.toolbox/bin/datanet-mcp",
      "args": [],
      "disabled": false,
      "timeout": 60
    },
    "aws-api-mcp": {
      "command": "/home/nflos/.config/smithy-mcp/mcp-servers/aws-api-mcp",
      "args": [],
      "disabled": false,
      "timeout": 60
    }
  }
}
```

## Additional Common Issues

### Issue: "Starting directory (cwd) does not exist"

**Solution:** Create the Desktop directory:
```bash
mkdir -p /home/nflos/Desktop
```

### Issue: Server Binary Not Found

**Symptom:**
```
Command not found: /home/nflos/.toolbox/bin/<server-name>
```

**Solutions:**
1. Install Toolbox if missing:
   ```bash
   toolbox bootstrap
   ```

2. Verify the server is installed:
   ```bash
   ls -la /home/nflos/.toolbox/bin/ | grep mcp
   ```

3. Install the specific MCP server if needed:
   ```bash
   toolbox install <server-name>
   ```

### Issue: Permission Denied

**Symptom:**
```
Permission denied: /home/nflos/.toolbox/bin/<server-name>
```

**Solution:** Make the binary executable:
```bash
chmod +x /home/nflos/.toolbox/bin/<server-name>
```

## Verification Steps

After making changes:

1. **Save the configuration file**

2. **Restart VS Code completely** (not just reload window):
   - Close VS Code
   - Reopen VS Code

3. **Check Cline MCP Servers section**:
   - Open Cline settings (gear icon ⚙️)
   - Scroll to "MCP Servers"
   - Verify all servers show green indicators

4. **Check Cline Output logs**:
   - View → Output
   - Select "Cline" from dropdown
   - Look for connection success messages
   - Should NOT see Java stack traces or JSON parse errors

5. **Test a server**:
   ```
   Can you search for "brazil" in internal documentation?
   ```

## Key Takeaways

1. **Always call Amazon MCP server binaries directly**
2. **Never use `aim mcp start-server` in MCP configuration**
3. **Direct binary calls prevent stdout pollution**
4. **Full paths required** (not just binary name)
5. **Restart VS Code after config changes**

## Quick Fix Script

Save this as `fix_amazon_mcp.sh`:

```bash
#!/bin/bash
# Fix Amazon MCP servers configuration

CONFIG_FILE=""

# Find the config file
if [ -f "$HOME/.vscode-server/data/User/globalStorage/asbx.amzn-cline/settings/cline_mcp_settings.json" ]; then
    CONFIG_FILE="$HOME/.vscode-server/data/User/globalStorage/asbx.amzn-cline/settings/cline_mcp_settings.json"
elif [ -f "$HOME/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json" ]; then
    CONFIG_FILE="$HOME/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json"
fi

if [ -z "$CONFIG_FILE" ]; then
    echo "❌ Could not find Cline MCP settings file"
    exit 1
fi

echo "📄 Found config file: $CONFIG_FILE"
echo "📦 Creating backup..."
cp "$CONFIG_FILE" "$CONFIG_FILE.backup"

# Create correct configuration
cat > "$CONFIG_FILE" <<'EOF'
{
  "mcpServers": {
    "builder-mcp": {
      "command": "/home/nflos/.toolbox/bin/builder-mcp",
      "args": [],
      "disabled": false,
      "timeout": 60
    },
    "aws-api-mcp": {
      "command": "/home/nflos/.config/smithy-mcp/mcp-servers/aws-api-mcp",
      "args": [],
      "disabled": false,
      "timeout": 60
    }
  }
}
EOF

echo "✅ Configuration fixed!"
echo "🔄 Please restart VS Code for changes to take effect"
echo "💾 Backup saved to: $CONFIG_FILE.backup"
```

Run with:
```bash
chmod +x fix_amazon_mcp.sh
./fix_amazon_mcp.sh
```

## For AI Assistants

When helping users with Amazon MCP connection issues:

1. **First check if they're using `aim` in the command**
2. **Look for Java stack traces or JSON parse errors**
3. **Replace `aim` configuration with direct binary paths**
4. **Verify binaries exist before recommending them**
5. **Always remind users to restart VS Code**
6. **Point them to this troubleshooting guide**

Remember: The most common cause of Amazon MCP server failures is using `aim mcp start-server` instead of calling the binary directly!
