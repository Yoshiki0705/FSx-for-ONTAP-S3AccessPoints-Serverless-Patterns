# AI Agent Demo Guide

🌐 **Language / 言語**: [日本語](ai-agent-demo-guide.md) | **English**

> End-to-end walkthrough from admin enablement to end-user AI interactions.

## Prerequisites

- Amplify sandbox deployed (`npx ampx sandbox --once`)
- Cognito user in `storage-admin` group (required for AI Settings toggle)
- (For semantic search) Bedrock Knowledge Base created, KB ID set in `portal-config.ts`

## Demo Scenarios

### Scenario 1: Enable AI Features (Admin)

1. Navigate to sidebar "Admin > Resource Management"
2. Click the "AI Settings" card in the "AI Services" category
3. Review cost information:
   - AI Agent: ✅ Ready (~$0.001/request)
   - Semantic Search: ⚙️ KB required (~$1-10/month with S3 Vectors)
4. Toggle "AI Agent" ON → "🤖 AI Agent" immediately appears in nav
5. (Optional) Toggle "Semantic Search" ON
6. Reload page → verify settings persist

### Scenario 2: File Operations with AI Agent

1. Navigate to "AI & Processing > AI Agent"
2. Mode selector: choose "📁 File Ops"
3. Click "Browse Folders" card → agent returns root folder listing
4. Type "search for log files in simulation/" → search_files tool executes
5. Verify `file-explorer` (blue) badge in tool trace timeline
6. Click 📜 → chat history panel opens (auto-saved)

### Scenario 3: Multimodal Image Input

1. Mode selector: choose "🤖 Multi-Agent"
2. Click 📎 or drag-and-drop an image onto the input area
3. Preview appears → type "Describe what's in this image"
4. Bedrock Vision API analyzes the image and generates a response

### Scenario 4: KB Mode Semantic Search

1. Mode selector: choose "🧠 KB Search"
2. Card grid filters to show only KB-related cards
3. Type "What are the thermal design temperature limits?"
4. kb_search tool executes → `knowledge-analyst` (purple) badge
5. Response includes source file path citations

### Scenario 5: File Permissions Sidebar

1. After the agent references files in conversation
2. Click 📂 → file sidebar expands
3. Click a referenced file chip
4. Security style, Owner/Group, UNIX permissions, ACL are displayed

### Scenario 6: Agent Directory Management

1. Navigate to "AI & Processing > Agent Registry"
2. "Agent Directory" tab → card grid (empty initially)
3. Click "+ Create New" → Agent Creator form
4. Fill in:
   - Icon: 🔬
   - Name: Log Analysis Agent
   - Description: Specialized in simulation log analysis
   - Category: analytics
   - System Prompt: "You are a simulation log analysis expert..."
   - Tools: check read_file, search_files
   - Shared: ON
5. Click "Create Agent" → returns to directory → card appears

### Scenario 7: Multi-Agent Team Creation

1. Switch to "🧩 Multi-Agent Teams" tab
2. Click "+ Create Team" → wizard opens
3. Fill in:
   - Team Name: Document Analysis Team
   - Description: Search and summarize technical docs
4. Select 2+ agents from the pool
5. Assign roles (Supervisor / Collaborator / Reviewer)
6. Click "Create Team" → team card appears in gallery

## Verification Checklist

| Feature | How to Verify | Expected Result |
|---------|--------------|-----------------|
| AI Settings toggle | Toggle ON/OFF | Nav items show/hide immediately |
| Mode selector | Switch pills | Card grid and prompt change |
| Chat history | 📜 panel | Past sessions listed, click to restore |
| Image upload | 📎 or D&D | Preview shows, Vision response |
| File sidebar | 📂 after file reference | Permission info (when ONTAP connected) |
| Agent Directory | Card grid | Search, filter, detail panel |
| Agent Creator | Form submission | Validation, successful creation |
| Teams wizard | Select agents + roles | Team created, gallery card shown |

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| AI Settings toggle error | Lambda not deployed | Re-run `npx ampx sandbox --once` |
| AI Agent not in nav | Not enabled or non-admin | Confirm storage-admin group → enable in AI Settings |
| KB search "not configured" | bedrockKbId empty | Set KB ID in portal-config.ts → redeploy |
| Image upload error | >5MB or unsupported format | Use jpeg/png/gif/webp under 5MB |
| File sidebar empty | ONTAP not connected | VPC Lambda + ONTAP management LIF required |
