output "knfsd_instance_ids" {
  description = "KNFSD proxy instance IDs"
  value       = aws_instance.knfsd[*].id
}

output "knfsd_private_ips" {
  description = "KNFSD proxy private IPs (use for NFS mount from clients)"
  value       = aws_instance.knfsd[*].private_ip
}

output "knfsd_public_ips" {
  description = "KNFSD proxy public IPs (if assigned)"
  value       = aws_instance.knfsd[*].public_ip
}

output "security_group_id" {
  description = "Security Group ID (add to client instances if needed)"
  value       = aws_security_group.knfsd.id
}

output "cluster_name" {
  description = "CLUSTER_NAME used for SSM Parameter Store path"
  value       = local.cluster_name
}

output "nfs_mount_commands" {
  description = "NFS mount commands for clients"
  value = length(aws_instance.knfsd) > 0 ? [
    for m in var.source_mounts :
    "sudo mount -t nfs -o vers=3 ${aws_instance.knfsd[0].private_ip}:${m.export} /mnt/knfsd${m.mount}"
  ] : []
}

output "ssm_parameter_path" {
  description = "SSM Parameter Store path for this cluster's configuration"
  value       = "/knfsd/${local.cluster_name}/"
}


output "fsid_mode" {
  description = "FSID management mode in use"
  value       = var.fsid_mode
}

output "fsid_db_endpoint" {
  description = "FSID database endpoint (external mode only)"
  value       = local.fsid_db_endpoint
  sensitive   = false
}
