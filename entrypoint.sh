#!/bin/bash

# Export environment variables for cron
printenv | grep -v "no_proxy" >> /etc/environment

# Create log file
touch /var/log/cron.log

echo "======================================"
echo "FTSE 100 Scraper Container Started"
echo "======================================"
echo "Schedule: Every 2 minutes"
echo "ClickHouse: ${CLICKHOUSE_HOST}:${CLICKHOUSE_PORT}"
echo "Database: ${CLICKHOUSE_DATABASE}"
echo "======================================"

# Run scraper once on startup
echo "[$(date)] Running initial scrape..."
python /app/scraper.py 2>&1 | tee -a /var/log/cron.log

echo "[$(date)] Initial scrape complete. Starting cron daemon..."

# Start cron daemon in foreground mode
# Using -f flag to run cron in foreground, keeping container alive
exec cron -f
