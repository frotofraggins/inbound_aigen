# MCP Setup Complete! ✅

## What Was Done

I've successfully configured **both** MCP servers for Cline:

### 1. Builder MCP ✅
- **Location**: `/home/nflos/.toolbox/bin/builder-mcp`
- **Version**: 2.14.1 (Toolbox 1.0.5581.0)
- **Purpose**: Amazon internal tools (search docs, access code repos, query systems)

### 2. AWS API MCP (Andes) ✅
- **Location**: `/home/nflos/.config/smithy-mcp/mcp-servers/aws-api-mcp`
- **Version**: 1.0.1737.0
- **Purpose**: AWS CLI operations and API calls

## Configuration File Created

Location: `~/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json`

```json
{
  "mcpServers": {
    "builder-mcp": {
      "command": "/home/nflos/.toolbox/bin/builder-mcp",
      "args": [],
      "disabled": false
    },
    "aws-api-mcp": {
      "command": "/home/nflos/.config/smithy-mcp/mcp-servers/aws-api-mcp",
      "args": [],
      "disabled": false
    }
  }
}
```

## Next Steps

### 1. Restart VS Code (Required!)
**You MUST restart VS Code completely for the changes to take effect.**

Options:
- Close VS Code completely and reopen it
- Or use Command Palette: `Developer: Reload Window`

### 2. Verify the Configuration

After restarting, check that both MCPs are working:

1. **Open Cline settings** (gear icon ⚙️ in Cline panel)
2. **Scroll to "MCP Servers" section**
3. **You should see**:
   - ✅ `builder-mcp` with green indicator
   - ✅ `aws-api-mcp` with green indicator

### 3. Test the MCPs

Try these test commands to verify both MCPs work:

**Test Builder MCP:**
```
Can you search for "brazil workspace" in internal documentation?
```

**Test AWS API MCP:**
```
Can you list my EC2 instances in us-west-2?
```

## For Your Other Cloud Desktop

To set up on a new cloud desktop, run these commands:

```bash
# Ensure toolbox is installed
toolbox bootstrap

# Verify both MCPs exist
which builder-mcp
ls -la /home/nflos/.config/smithy-mcp/mcp-servers/aws-api-mcp

# Create Cline MCP configuration
mkdir -p ~/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings

cat > ~/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json <<'EOF'
{
  "mcpServers": {
    "builder-mcp": {
      "command": "/home/nflos/.toolbox/bin/builder-mcp",
      "args": [],
      "disabled": false
    },
    "aws-api-mcp": {
      "command": "/home/nflos/.config/smithy-mcp/mcp-servers/aws-api-mcp",
      "args": [],
      "disabled": false
    }
  }
}
EOF

# Restart VS Code
```

## Troubleshooting

If you don't see the MCPs after restarting:

1. **Check Cline Output logs**:
   - Open Output panel (View → Output)
   - Select "Cline" from dropdown
   - Look for connection errors

2. **Verify configuration file exists**:
   ```bash
   cat ~/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json
   ```

3. **Test MCPs directly**:
   ```bash
   builder-mcp --version
   /home/nflos/.config/smithy-mcp/mcp-servers/aws-api-mcp --version
   ```

## What You Can Do Now

With both MCPs configured, you can:

### Builder MCP Tools:
- Search Amazon internal documentation
- Access code repositories
- Query internal systems (SIM tickets, pipelines, etc.)
- Read internal websites
- Workspace operations

### AWS API MCP Tools:
- Execute AWS CLI commands
- List and manage AWS resources
- Query CloudWatch logs
- Work with EC2, S3, Lambda, etc.
- All AWS service operations

## Additional Documentation

See `BUILDER_MCP_SETUP_GUIDE.md` for detailed setup instructions, troubleshooting, and advanced configuration options.
