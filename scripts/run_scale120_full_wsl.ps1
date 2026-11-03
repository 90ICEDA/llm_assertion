param(
    [string]$Distro = "Ubuntu"
)

$repo = "/mnt/d/AssertionForge-main1"
$script = "bash $repo/scripts/run_scale120_full_wsl.sh"

Write-Host "Running full scale120 WSL recheck on distro '$Distro'..."
wsl.exe -d $Distro --cd $repo bash -lc $script
