param(
  [string]$Namespace = "supplymind",
  [string]$Release = "supplymind",
  [int]$RollbackRevision = 1,
  [switch]$RunCluster
)

$ErrorActionPreference = "Stop"
helm lint infra/helm/supplymind
helm template $Release infra/helm/supplymind | Out-Null
if ($RunCluster) {
  helm upgrade --install $Release infra/helm/supplymind --namespace $Namespace --create-namespace --wait --timeout 5m
  helm history $Release --namespace $Namespace
  helm rollback $Release $RollbackRevision --namespace $Namespace --wait --timeout 5m
}
Write-Output "Helm lint/template passed. Cluster install/rollback runs only with -RunCluster."
