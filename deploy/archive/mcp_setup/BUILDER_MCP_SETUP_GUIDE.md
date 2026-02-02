# Builder MCP Setup Guide for Cloud Desktop

## Current Status on This System ✅

Your builder-mcp is installed and working:
- **Location**: `/home/nflos/.toolbox/bin/builder-mcp`
- **Version**: 2.14.1 (Toolbox 1.0.5581.0)
- **VS Code**: 1.108.1

## Setting Up Builder MCP in Cline

### Step 1: Configure MCP in Cline Settings

1. **Open Cline Settings**:
   - Click on the Cline icon in VS Code sidebar
   - Click the gear icon (⚙️) at the top of Cline panel
   - Or use Command Palette: `Cline: Open Settings`

2. **Navigate to MCP Settings**:
   - Scroll down to "MCP Servers" section
   - Click "Edit MCP Settings" or "Add MCP Server"

3. **Add Builder MCP Configuration**:
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

### Step 2: Verify Installation

After adding the configuration, you should see:
- Builder MCP listed in Cline's MCP servers section
- A green indicator showing it's connected
- Available tools in Cline's tool list

### Step 3: Test the Connection

Try asking Cline to use a Builder tool:
```
Can you search for "brazil workspace" in internal documentation?
```

## Common Issues & Solutions

### Issue 1: MCP Server Not Starting

**Symptoms**: Red indicator, "Failed to connect" error

**Solutions**:
1. **Verify builder-mcp path**:
   ```bash
   which builder-mcp
   # Should output: /home/nflos/.toolbox/bin/builder-mcp
   ```

2. **Test builder-mcp directly**:
   ```bash
   builder-mcp --version
   # Should show version info
   ```

3. **Check permissions**:
   ```bash
   ls -la /home/nflos/.toolbox/bin/builder-mcp
   # Should be executable (rwxr-xr-x)
   ```

### Issue 2: "Command not found" Error

**Solution**: Ensure full path is used in config:
- ✅ Use: `/home/nflos/.toolbox/bin/builder-mcp`
- ❌ Don't use: `builder-mcp` or `~/toolbox/bin/builder-mcp`

### Issue 3: Toolbox Not Installed

If `builder-mcp --version` fails, you need to install Toolbox:

```bash
# Install Amazon Toolbox
toolbox bootstrap
```

### Issue 4: MCP Settings File Location

Cline stores MCP settings in one of these locations:
- **VS Code**: `~/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json`
- **Cursor**: `~/.config/Cursor/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json`

You can manually edit this file if needed.

### Issue 5: Need to Restart

After configuration changes:
1. Restart VS Code completely (don't just reload window)
2. Or use Command Palette: `Developer: Reload Window`

## Setting Up on a New Cloud Desktop

### Quick Setup Script

Create this script to automate setup on new cloud desktops:

```bash
#!/bin/bash
# save as: setup_builder_mcp.sh

echo "🔧 Setting up Builder MCP for Cline..."

# 1. Verify toolbox is installed
if ! command -v builder-mcp &> /dev/null; then
    echo "❌ builder-mcp not found. Installing Toolbox..."
    toolbox bootstrap
fi

# 2. Verify builder-mcp works
echo "✓ Builder MCP location: $(which builder-mcp)"
builder-mcp --version

# 3. Find Cline settings location
CLINE_SETTINGS=""
if [ -d "$HOME/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline" ]; then
    CLINE_SETTINGS="$HOME/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings"
elif [ -d "$HOME/.config/Cursor/User/globalStorage/rooveterinaryinc.roo-cline" ]; then
    CLINE_SETTINGS="$HOME/.config/Cursor/User/globalStorage/rooveterinaryinc.roo-cline/settings"
fi

if [ -n "$CLINE_SETTINGS" ]; then
    echo "✓ Found Cline settings at: $CLINE_SETTINGS"
    
    # Create settings directory if needed
    mkdir -p "$CLINE_SETTINGS"
    
    # Create MCP config
    cat > "$CLINE_SETTINGS/cline_mcp_settings.json" <<EOF
{
  "mcpServers": {
    "builder-mcp": {
      "command": "$(which builder-mcp)",
      "args": [],
      "disabled": false
    }
  }
}
EOF
    echo "✓ Created MCP configuration"
else
    echo "⚠️  Cline settings directory not found. Please configure manually."
fi

echo "✅ Setup complete! Restart VS Code to apply changes."
```

### Manual Setup Steps

1. **On OLD desktop** (working system):
   ```bash
   # Export your Cline MCP settings
   cat ~/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json
   ```

2. **On NEW desktop**:
   ```bash
   # Ensure toolbox is installed
   toolbox bootstrap
   
   # Verify builder-mcp
   which builder-mcp
   builder-mcp --version
   
   # Create settings directory
   mkdir -p ~/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings
   
   # Create MCP config (paste from old desktop or create new)
   cat > ~/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json <<'EOF'
{
  "mcpServers": {
    "builder-mcp": {
      "command": "/home/nflos/.toolbox/bin/builder-mcp",
      "args": [],
      "disabled": false
    }
  }
}
EOF
   ```

3. **Restart VS Code**

## Verification Checklist

Use this checklist to verify everything is working:

- [ ] `which builder-mcp` returns a path
- [ ] `builder-mcp --version` shows version info
- [ ] Cline settings file exists
- [ ] Builder MCP appears in Cline's MCP servers list
- [ ] Green indicator shows connection is active
- [ ] Can use builder-mcp tools (e.g., "search internal docs")

## Advanced Configuration

### Adding Additional MCP Servers

You can have multiple MCP servers:

```json
{
  "mcpServers": {
    "builder-mcp": {
      "command": "/home/nflos/.toolbox/bin/builder-mcp",
      "args": [],
      "disabled": false
    },
    "datanet-mcp": {
      "command": "/home/nflos/.toolbox/bin/mcp-registry",
      "args": ["start-server", "datanet-mcp"],
      "disabled": false
    }
  }
}
```

### Environment Variables

If you need to pass environment variables:

```json
{
  "mcpServers": {
    "builder-mcp": {
      "command": "/home/nflos/.toolbox/bin/builder-mcp",
      "args": [],
      "env": {
        "CUSTOM_VAR": "value"
      },
      "disabled": false
    }
  }
}
```

## Getting Help

If you're still having issues:

1. **Check Cline logs**:
   - Open Output panel in VS Code
   - Select "Cline" from dropdown
   - Look for MCP connection errors

2. **Check builder-mcp logs**:
   ```bash
   # Run builder-mcp with debug output
   DEBUG=* /home/nflos/.toolbox/bin/builder-mcp
   ```

3. **Test builder-mcp standalone**:
   ```bash
   # Test it works outside of Cline
   echo '{"jsonrpc":"2.0","method":"initialize","params":{},"id":1}' | builder-mcp
   ```

4. **Ask for help**:
   - Check #builder-tools Slack channel
   - File a ticket if it's a bug

## Next Steps

Once builder-mcp is working, you can:
- Search internal Amazon documentation
- Access code repositories
- Query internal systems
- Use Amazon-specific tools directly from Cline

For more information about available tools, see the MCP section in your Cline interface.
