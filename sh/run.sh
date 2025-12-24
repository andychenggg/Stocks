#!/bin/bash
cd /root/code/stocks-deploy
/root/miniforge3/envs/tools/bin/python /root/code/stocks-deploy/whop_summary.py >> /root/code/stocks-deploy/logs/whop.logs 2>&1