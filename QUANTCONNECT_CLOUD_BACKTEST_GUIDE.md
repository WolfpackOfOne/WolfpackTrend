# QuantConnect Cloud Backtest Guide for AI Agents

This guide documents how to run cloud backtests on QuantConnect using browser automation tools (Claude in Chrome MCP).

## Prerequisites

1. User must be logged into QuantConnect at `https://www.quantconnect.com/terminal/`
2. Project must exist on QuantConnect cloud (check `config.json` for `cloud-id`)
3. Browser automation tools (Claude in Chrome MCP) must be available

## Step-by-Step Process

### 1. Initialize Browser Tab

```
# First, get the browser context
mcp__Claude_in_Chrome__tabs_context_mcp with createIfEmpty: true

# This returns available tabs and creates a tab group if needed
```

### 2. Check Project Configuration

Read the local project's `config.json` to get the cloud project ID:

```json
{
    "cloud-id": 12345678,  // Replace with your QuantConnect project ID
    "organization-id": "your-organization-id"
}
```

### 3. Navigate to the Project

Navigate directly to the project using the cloud-id:

```
mcp__Claude_in_Chrome__navigate
url: https://www.quantconnect.com/project/{cloud-id}
```

Example: `https://www.quantconnect.com/project/{cloud-id}`

### 4. Handle Organization Switching

QuantConnect projects are tied to organizations. If the project doesn't load:

1. The page may show an "organization switch" dialog
2. Click on the correct organization name (found in `config.json` as `organization-id`)
3. Wait for the IDE to load

### 5. Wait for IDE to Load

The QuantConnect IDE takes a few seconds to fully load:

1. Wait 2-3 seconds after navigation
2. Take a screenshot to verify the code editor is visible
3. Look for the `main.py` tab and the code content

### 6. Locate the Backtest Button

The backtest button is in the toolbar above the code editor. It's a **play icon** (triangle pointing right).

**Toolbar location**: Top-right of the code editor area, approximately at coordinates `(1007, 57)` on a standard viewport.

The toolbar contains (left to right):
- Gear icon (settings)
- **First play icon** - Run Backtest (this is the one to click)
- Second play icon - Debug/step through
- Lightning icon - Live deployment
- Other toolbar buttons

### 7. Run the Backtest

Click the first play icon in the toolbar:

```
mcp__Claude_in_Chrome__computer
action: left_click
coordinate: [1007, 57]  # Adjust based on viewport
tabId: {your_tab_id}
```

### 8. Monitor Backtest Progress

After clicking, a modal appears showing:

1. **"Requesting Backtest"** - Initial request (completes quickly)
2. **"Launching Backtest"** - Deploying to cloud node
3. **"Waiting for Results"** - Backtest running

The backtest name is randomly generated (e.g., "Ugly Apricot Termite").

### 9. Wait for Completion

Wait 10-30 seconds depending on backtest complexity:

```bash
sleep 10  # Adjust based on backtest duration
```

Then take a screenshot to see results.

### 10. Read Backtest Results

Once complete, the results page shows:

- **Equity**: Final portfolio value
- **Return**: Percentage return
- **PSR**: Probabilistic Sharpe Ratio
- **Fees**: Total trading fees
- **Equity Chart**: Visual performance over time

## Key Element References

| Element | How to Find | Notes |
|---------|-------------|-------|
| Project list | `mcp__Claude_in_Chrome__find` query: "See All Projects" | Links to project browser |
| Project name | `mcp__Claude_in_Chrome__find` query: "{ProjectName}" | Click to open project |
| main.py tab | Click on tab at top of editor | Shows code |
| Backtest button | Coordinate click at ~(1007, 57) | First play icon in toolbar |
| Backtest Results tab | Appears after backtest starts | Shows results |

## Troubleshooting

### Project Won't Load
- Check if correct organization is selected
- Verify `cloud-id` exists in config.json
- Try navigating directly to `/project/{cloud-id}`

### Can't Find Backtest Button
- Ensure main.py or code file is open (click the tab)
- The toolbar only appears when viewing code files
- Use coordinate click as fallback: `[1007, 57]`

### Backtest Fails to Start
- Check Cloud Terminal for error messages
- Verify project builds successfully (look for "Built project" message)
- Ensure sufficient QuantConnect credits/subscription

### Organization Issues
- Projects belong to specific organizations
- Use the organization dropdown or switch dialog
- The organization-id in config.json must match

## Example Complete Workflow

```python
# 1. Initialize
tabs_context_mcp(createIfEmpty=True)

# 2. Navigate to project
navigate(tabId=tab_id, url="https://www.quantconnect.com/project/{cloud-id}")

# 3. Wait for load
sleep(3)

# 4. Click main.py tab (if not already open)
computer(action="left_click", coordinate=[424, 57], tabId=tab_id)

# 5. Click backtest button
computer(action="left_click", coordinate=[1007, 57], tabId=tab_id)

# 6. Wait for results
sleep(15)

# 7. Screenshot to see results
computer(action="screenshot", tabId=tab_id)
```

## Notes for Future Agents

1. **Always take screenshots** - The QuantConnect UI is complex; screenshots help verify state
2. **Coordinate clicks work well** - The toolbar buttons don't have good accessibility labels
3. **Be patient** - The IDE and backtests take time to load/run
4. **Check the Cloud Terminal** - It shows build status, errors, and backtest logs
5. **Project IDs are stable** - Use `config.json` cloud-id for reliable navigation
