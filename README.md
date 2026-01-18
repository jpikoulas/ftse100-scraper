# FTSE 100 Stock Scraper

A containerized application that scrapes FTSE 100 constituent data from the London Stock Exchange website and stores it in ClickHouse.

## Features

- Scrapes all 100 FTSE 100 stocks across 5 pages
- Extracts: Code, Name, Currency, Market Cap, Price, Change, Change %
- Stores data in ClickHouse database
- Runs automatically every 2 minutes via cron
- Runs as a background Docker container

## Data Fields

| Field | Type | Description |
|-------|------|-------------|
| code | String | Stock ticker code (e.g., "SHEL") |
| name | String | Company name |
| currency | String | Trading currency (GBX, USD, EUR) |
| market_cap | Float64 | Market capitalization in millions |
| price | Float64 | Current stock price |
| change | Float64 | Price change |
| change_pct | Float64 | Percentage change |
| scraped_at | DateTime | Timestamp of when data was scraped |

## Prerequisites

- Docker and Docker Compose
- ClickHouse database accessible from the container

## Configuration

Environment variables (set in `docker-compose.yml`):

| Variable | Default | Description |
|----------|---------|-------------|
| CLICKHOUSE_HOST | 10.10.1.30 | ClickHouse server hostname |
| CLICKHOUSE_PORT | 8333 | ClickHouse HTTP port |
| CLICKHOUSE_USER | johnp | ClickHouse username |
| CLICKHOUSE_PASSWORD | test123 | ClickHouse password |
| CLICKHOUSE_DATABASE | garden | Database name |

## Quick Start

### 1. Clone and configure

```bash
cd /Users/johnp/repos/ftse100-scraper
```

Edit `docker-compose.yml` if you need to change the ClickHouse connection settings.

### 2. Build and run

```bash
# Build and start in background (detached mode)
docker compose up -d --build

# View logs
docker compose logs -f

# Check container status
docker compose ps
```

### 3. Verify it's working

```bash
# Check container logs
docker logs ftse100-scraper

# Check cron is running inside container
docker exec ftse100-scraper ps aux | grep cron

# View scraper logs
docker exec ftse100-scraper tail -f /var/log/cron.log
```

## Usage Commands

### Start the scraper
```bash
docker compose up -d --build
```

### Stop the scraper
```bash
docker compose down
```

### Restart the scraper
```bash
docker compose restart
```

### View real-time logs
```bash
docker compose logs -f
```

### Run scraper manually (inside container)
```bash
docker exec ftse100-scraper python /app/scraper.py
```

### Check ClickHouse data
```sql
-- Connect to ClickHouse and run:
SELECT * FROM garden.ftse100_indexes ORDER BY scraped_at DESC LIMIT 10;

-- Count records by scrape time
SELECT scraped_at, count() as stocks
FROM garden.ftse100_indexes
GROUP BY scraped_at
ORDER BY scraped_at DESC
LIMIT 10;

-- Get latest prices for all stocks
SELECT code, name, currency, price, change_pct, scraped_at
FROM garden.ftse100_indexes
WHERE scraped_at = (SELECT max(scraped_at) FROM garden.ftse100_indexes)
ORDER BY price DESC;
```

## Project Structure

```
ftse100-scraper/
├── docker-compose.yml    # Docker Compose configuration
├── Dockerfile            # Container build instructions
├── scraper.py            # Main scraper application
├── requirements.txt      # Python dependencies
├── crontab               # Cron schedule (every 2 minutes)
├── entrypoint.sh         # Container startup script
└── README.md             # This file
```

## How It Works

1. **Container starts** - `entrypoint.sh` runs initial scrape and starts cron daemon
2. **Selenium scraping** - Headless Chrome navigates LSE website and extracts data
3. **Pagination** - Automatically clicks through all 5 pages to get 100 stocks
4. **ClickHouse storage** - Data inserted into `ftse100_indexes` table
5. **Cron scheduling** - Process repeats every 2 minutes

## Troubleshooting

### Container exits immediately
```bash
# Check logs for errors
docker compose logs

# Rebuild if needed
docker compose down && docker compose up -d --build
```

### No data in ClickHouse
```bash
# Check if scraper can reach ClickHouse
docker exec ftse100-scraper python -c "import clickhouse_connect; c = clickhouse_connect.get_client(host='10.10.1.30', port=8333, username='johnp', password='test123'); print(c.ping())"
```

### Scraper not getting all 100 stocks
- The LSE website uses JavaScript pagination
- The scraper uses multiple click methods to handle Angular components
- Check logs for pagination warnings

## Integration with Superset

This scraper is designed to work with Apache Superset for visualization. See the companion project at `/Users/johnp/repos/Superset-app` which includes:

- Superset Docker setup with ClickHouse connector
- Pre-configured charts and dashboard
- API script to create visualizations programmatically

Dashboard URL: http://localhost:8088/superset/dashboard/1/

## License

MIT
