# $loc = "$(Get-Location)" && `

podman run `
    --privileged `
    --detach `
    --name=tljh-dev `
    --publish 12000:80 `
    --mount type=bind,source=.,target=/srv/src `
    tljh-systemd