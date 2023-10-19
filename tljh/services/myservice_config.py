# in tljh this goes into /opt/tljh/config/jupyterhub_config.d/myservice_config.py
import sys

c = get_config()  # noqa

c.JupyterHub.load_roles.append(
    {
        "name": "get-users-idle",
        "scopes": [
            "read:users:activity", # read user last_activity
            "servers", # start and stop servers
            # 'admin:users' # needed if culling idle users as well
            "list:users",
        ]
    }
)

c.JupyterHub.services.append(
    {
        "name": "get-users-idle",
        "admin": True,
        "command": [sys.executable, "-m", "myservice", "--timeout=3600"],
    }
)