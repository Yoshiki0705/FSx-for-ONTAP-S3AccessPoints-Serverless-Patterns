# Dual-Access Demo — NFS + S3 AP Simultaneous View

> Shows the same file visible via NFS mount AND S3 AP simultaneously (the core value proposition).

## Prerequisites

- EC2 instance with NFS mount to FSx for ONTAP volume
- S3 AP alias configured in portal

## Demo Script (tmux split-pane)

```bash
#!/bin/bash
# dual-access-demo.sh — Split terminal showing NFS + S3 AP access to same file

# Start tmux session with two panes
tmux new-session -d -s demo

# Left pane: NFS access
tmux send-keys -t demo "echo '=== NFS Mount ===' && ls -la /mnt/fsxn/contracts/ && echo '---' && cat /mnt/fsxn/contracts/sample.txt" Enter

# Right pane: S3 AP access
tmux split-window -h -t demo
tmux send-keys -t demo "echo '=== S3 AP Access ===' && aws s3api list-objects-v2 --bucket <s3ap-alias> --prefix contracts/ --max-items 5 && echo '---' && aws s3api get-object --bucket <s3ap-alias> --key contracts/sample.txt /dev/stdout" Enter

tmux attach -t demo
```

## What to Show

1. **Same file, two protocols**: `contracts/sample.txt` visible via both NFS `cat` and S3 AP `get-object`
2. **Real-time sync**: Write via NFS → immediately visible via S3 AP (no sync delay)
3. **Portal view**: Open browser showing the same `contracts/` folder in File Portal

## Key Talking Points

- "No data copy, no sync agent, no ETL pipeline"
- "Existing NFS/SMB clients continue working unchanged"
- "S3 AP provides the programmatic access layer for AI/Lambda"
- "Same ONTAP permissions govern both access paths"

## Screenshot Approach

Take a screenshot with:
- Left: Terminal showing `ls /mnt/fsxn/contracts/`
- Right: Portal File Explorer showing same `contracts/` directory
- Caption: "Same data, two access paths — NFS for workstations, S3 AP for AI processing"
