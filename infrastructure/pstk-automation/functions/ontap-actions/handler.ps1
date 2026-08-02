# ═══════════════════════════════════════════════════════════════════
# FSx for ONTAP — Lambda PowerShell Handler (Custom Runtime)
# 
# This handler dispatches ONTAP management actions via PSTK cmdlets.
# Deployed as AWS Lambda with PowerShell custom runtime.
#
# Environment Variables:
#   FSX_MGMT_IP  — FSx for ONTAP management endpoint IP
#   SVM_NAME     — Target SVM name
#   SECRET_ARN   — Secrets Manager ARN for fsxadmin credentials
# ═══════════════════════════════════════════════════════════════════

#Requires -Modules @{ ModuleName='NetApp.ONTAP'; ModuleVersion='9.13.1' }
#Requires -Modules @{ ModuleName='AWS.Tools.SecretsManager'; ModuleVersion='4.1.0' }

Import-Module NetApp.ONTAP -Force
Import-Module AWS.Tools.SecretsManager -Force

# ─── Helper: Connect to FSx for ONTAP ───
function Connect-FsxOntap {
    $mgmtIp = $env:FSX_MGMT_IP
    $secretArn = $env:SECRET_ARN

    # Retrieve credentials from Secrets Manager
    $secretValue = Get-SECSecretValue -SecretId $secretArn
    $secret = $secretValue.SecretString | ConvertFrom-Json

    $securePass = ConvertTo-SecureString $secret.password -AsPlainText -Force
    $credential = New-Object PSCredential($secret.username, $securePass)

    # Connect
    $controller = Connect-NcController -Name $mgmtIp -Credential $credential -HTTPS -Timeout 30
    return $controller
}

# ─── Action: List CIFS Shares ───
function Invoke-ListShares {
    param([hashtable]$Params)
    $svmName = if ($Params.svm) { $Params.svm } else { $env:SVM_NAME }

    $shares = Get-NcCifsShare -VserverContext $svmName |
        Where-Object { $_.ShareName -notin @('c$', 'ipc$') } |
        Select-Object ShareName, Path, Comment

    return @{
        statusCode = 200
        body = @{ shares = $shares; count = $shares.Count } | ConvertTo-Json -Depth 5
    }
}

# ─── Action: Create CIFS Share ───
function Invoke-CreateShare {
    param([hashtable]$Params)
    $svmName = if ($Params.svm) { $Params.svm } else { $env:SVM_NAME }

    if (-not $Params.name -or -not $Params.path) {
        return @{ statusCode = 400; body = '{"error":"name and path are required"}' }
    }

    $share = Add-NcCifsShare -Name $Params.name -Path $Params.path `
        -VserverContext $svmName

    # Set ACL if provided
    if ($Params.acl) {
        foreach ($ace in $Params.acl) {
            Add-NcCifsShareAcl -Share $Params.name `
                -UserOrGroup $ace.userOrGroup `
                -Permission $ace.permission `
                -UserGroupType "windows" `
                -VserverContext $svmName
        }
    }

    return @{
        statusCode = 201
        body = @{ message = "Share '$($Params.name)' created"; share = $share } | ConvertTo-Json -Depth 5
    }
}

# ─── Action: List Local Users ───
function Invoke-ListUsers {
    param([hashtable]$Params)
    $svmName = if ($Params.svm) { $Params.svm } else { $env:SVM_NAME }

    $users = Get-NcCifsLocalUser -VserverContext $svmName |
        Select-Object UserName, FullName, Description, AccountDisabled

    return @{
        statusCode = 200
        body = @{ users = $users; count = $users.Count } | ConvertTo-Json -Depth 5
    }
}

# ─── Action: Create Local User ───
function Invoke-CreateUser {
    param([hashtable]$Params)
    $svmName = if ($Params.svm) { $Params.svm } else { $env:SVM_NAME }

    if (-not $Params.username -or -not $Params.password) {
        return @{ statusCode = 400; body = '{"error":"username and password are required"}' }
    }

    $secPw = ConvertTo-SecureString $Params.password -AsPlainText -Force
    $user = New-NcCifsLocalUser -VserverContext $svmName `
        -UserName $Params.username `
        -FullName ($Params.fullName ?? "") `
        -Description ($Params.description ?? "") `
        -Password $secPw

    return @{
        statusCode = 201
        body = @{ message = "User '$($Params.username)' created" } | ConvertTo-Json
    }
}

# ─── Action: List Volumes ───
function Invoke-ListVolumes {
    param([hashtable]$Params)
    $svmName = if ($Params.svm) { $Params.svm } else { $env:SVM_NAME }

    $volumes = Get-NcVol -VserverContext $svmName |
        Where-Object { -not $_.VolumeStateAttributes.IsVserverRoot } |
        Select-Object Name, @{N='SizeGB';E={[math]::Round($_.TotalSize/1GB,2)}},
            @{N='UsedGB';E={[math]::Round($_.Used/1GB,2)}},
            @{N='AvailableGB';E={[math]::Round($_.Available/1GB,2)}},
            JunctionPath

    return @{
        statusCode = 200
        body = @{ volumes = $volumes; count = $volumes.Count } | ConvertTo-Json -Depth 5
    }
}

# ─── Action: List Snapshots ───
function Invoke-ListSnapshots {
    param([hashtable]$Params)
    $svmName = if ($Params.svm) { $Params.svm } else { $env:SVM_NAME }

    if (-not $Params.volume) {
        return @{ statusCode = 400; body = '{"error":"volume parameter is required"}' }
    }

    $snapshots = Get-NcSnapshot -Volume $Params.volume -VserverContext $svmName |
        Select-Object Name, Created, @{N='SizeMB';E={[math]::Round($_.Total/1MB,2)}}

    return @{
        statusCode = 200
        body = @{ snapshots = $snapshots; volume = $Params.volume; count = $snapshots.Count } | ConvertTo-Json -Depth 5
    }
}

# ─── Action: Create Snapshot ───
function Invoke-CreateSnapshot {
    param([hashtable]$Params)
    $svmName = if ($Params.svm) { $Params.svm } else { $env:SVM_NAME }

    if (-not $Params.volume -or -not $Params.name) {
        return @{ statusCode = 400; body = '{"error":"volume and name are required"}' }
    }

    $snapshot = New-NcSnapshot -Volume $Params.volume -Snapshot $Params.name `
        -VserverContext $svmName

    return @{
        statusCode = 201
        body = @{ message = "Snapshot '$($Params.name)' created on volume '$($Params.volume)'" } | ConvertTo-Json
    }
}

# ─── Action: List Export Policies ───
function Invoke-ListExportPolicies {
    param([hashtable]$Params)
    $svmName = if ($Params.svm) { $Params.svm } else { $env:SVM_NAME }

    $policies = Get-NcExportPolicy -VserverContext $svmName |
        Select-Object PolicyName, PolicyId

    return @{
        statusCode = 200
        body = @{ policies = $policies; count = $policies.Count } | ConvertTo-Json -Depth 5
    }
}

# ─── Action: Get SVM Status ───
function Invoke-GetSvmStatus {
    param([hashtable]$Params)
    $svmName = if ($Params.svm) { $Params.svm } else { $env:SVM_NAME }

    $svm = Get-NcVserver -Name $svmName
    $cifsServer = Get-NcCifsServer -VserverContext $svmName -ErrorAction SilentlyContinue

    $status = @{
        name = $svm.Vserver
        state = $svm.State
        type = $svm.VserverType
        protocols = $svm.AllowedProtocols
        cifsServer = if ($cifsServer) { $cifsServer.CifsServerName } else { $null }
        cifsDomain = if ($cifsServer) { $cifsServer.Domain } else { $null }
    }

    return @{
        statusCode = 200
        body = $status | ConvertTo-Json -Depth 3
    }
}

# ═══════════════════════════════════════════════════════════════════
# Lambda Entry Point
# ═══════════════════════════════════════════════════════════════════

function handler {
    param($LambdaInput, $LambdaContext)

    try {
        # Connect to FSx for ONTAP
        $null = Connect-FsxOntap

        # Parse action from event
        $action = $LambdaInput.action
        $params = if ($LambdaInput.params) { $LambdaInput.params } else { @{} }

        # Dispatch
        $result = switch ($action) {
            'listShares'          { Invoke-ListShares -Params $params }
            'createShare'         { Invoke-CreateShare -Params $params }
            'listUsers'           { Invoke-ListUsers -Params $params }
            'createUser'          { Invoke-CreateUser -Params $params }
            'listVolumes'         { Invoke-ListVolumes -Params $params }
            'listSnapshots'       { Invoke-ListSnapshots -Params $params }
            'createSnapshot'      { Invoke-CreateSnapshot -Params $params }
            'listExportPolicies'  { Invoke-ListExportPolicies -Params $params }
            'getSvmStatus'        { Invoke-GetSvmStatus -Params $params }
            default {
                @{
                    statusCode = 400
                    body = @{
                        error = "Unknown action: $action"
                        availableActions = @(
                            'listShares', 'createShare',
                            'listUsers', 'createUser',
                            'listVolumes',
                            'listSnapshots', 'createSnapshot',
                            'listExportPolicies',
                            'getSvmStatus'
                        )
                    } | ConvertTo-Json
                }
            }
        }

        return $result
    }
    catch {
        return @{
            statusCode = 500
            body = @{ error = $_.Exception.Message; type = $_.Exception.GetType().Name } | ConvertTo-Json
        }
    }
}
