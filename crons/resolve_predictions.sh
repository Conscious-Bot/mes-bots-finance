#!/bin/bash
cd /Users/olivierlegendre/mes-bots-finance
source venv/bin/activate
python -m intelligence.learning resolve >> data/resolve.log 2>&1
