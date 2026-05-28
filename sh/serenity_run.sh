#!/bin/bash
cd /root/code/stocks-deploy
/root/miniforge3/envs/tools/bin/python /root/code/stocks-deploy/serenity_summary.py >> /root/code/stocks-deploy/logs/serenity.logs 2>&1
