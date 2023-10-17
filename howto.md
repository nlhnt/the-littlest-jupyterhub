Follow the instructions [here](https://tljh.jupyter.org/en/latest/contributing/dev-setup.html).

## from inside the container run
`python3 /srv/src/bootstrap/bootstrap.py --admin admin:password`  
,where password is your admin password, or you can skip it for defaults (admin/admin), e.g.:
`python3 /srv/src/bootstrap/bootstrap.py --admin adminame:welcome123`  


## Copied from the instructions:
Make some changes to the repository. You can test easily depending on what you changed.  
* If you changed the `bootstrap/bootstrap.py` script or any of its dependencies, you can test it by running python3 `/srv/src/bootstrap/bootstrap.py`.  
* If you changed the `tljh/installer.py` code (or any of its dependencies), you can test it by running `python3 -m tljh.installer`.  
* If you changed `tljh/jupyterhub_config.py`, `tljh/configurer.py`, `/opt/tljh/config/` or any of their dependencies, you only need to restart jupyterhub for them to take effect. `tljh-config` reload hub should do that. (Try calling `which tljh-config`).  