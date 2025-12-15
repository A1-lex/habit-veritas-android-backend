# Habit Tracker Backend

RESTful API backend for the Habit Tracker Android application: https://github.com/A1-lex/habit-veritas. Built with Flask and SQLite.

## 🔗 Related Repository

**Android App**: https://github.com/A1-lex/habit-veritas

## 📋 Features

- **Habit Management**: Create, read, update, delete, and archive habits
- **Event Logging**: Track habit completions and skips with timestamps
- **Undo Functionality**: Revert recent events within a time window
- **Daily Aggregation**: Efficient daily statistics computation
- **Analytics**: Comprehensive metrics including streaks, completion rates, and trends
- **Soft Archiving**: Hide habits without permanent deletion
- **Duplicate Prevention**: Case-insensitive unique habit names

## 🛠️ Tech Stack

- **Framework**: Flask 3.1.2
- **Database**: SQLite3
- **Language**: Python 3.12

![Python](https://img.shields.io/badge/python-3.12-blue) ![Flask](https://img.shields.io/badge/flask-3.1.2-green)

## 📂 Project Structure

```
backend/
├── app.py              # Main Flask application
├── requirements.txt    # Python dependencies
├── habits.db          # SQLite database (auto-generated)
└── venv/              # Virtual environment (not tracked)
```

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- pip

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/A1-lex/habit-veritas-android-backend
   cd habit-veritas-android-backend
   ```

2. **Create virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the server**
   ```bash
   python app.py
   # Or use Flask CLI:
   flask run
   ```

   Server runs on `http://127.0.0.1:5000`

## 📡 API Endpoints

### Habits

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/habits` | Create new habit |
| `GET` | `/habits` | List all active habits |
| `GET` | `/habits/<id>` | Get single habit |
| `PUT` | `/habits/<id>` | Update habit (partial) |
| `DELETE` | `/habits/<id>` | Delete habit permanently |
| `POST` | `/habits/<id>/archive` | Archive habit (soft delete) |
| `POST` | `/habits/<id>/unarchive` | Restore archived habit |
| `GET` | `/habits/archived` | List archived habits |

### Events

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/events` | Log habit event (complete/skip) |
| `POST` | `/events/undo` | Undo last event within time window |

### Status

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/habit_status_today/<id>` | Today's status for one habit |
| `GET` | `/today_status_all` | Today's status for all habits |

### Analytics

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/analytics` | Comprehensive analytics summary |
| `GET` | `/analytics/summary` | Same as above (alias) |

## 📊 Database Schema

### `habits`
```sql
id              INTEGER PRIMARY KEY
name            TEXT NOT NULL UNIQUE
description     TEXT DEFAULT ''
active          INTEGER DEFAULT 1
archived_at     TEXT DEFAULT NULL
created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
```

### `habit_logs`
```sql
id              INTEGER PRIMARY KEY
user_uuid       TEXT
habit_id        INTEGER
event_type      TEXT (complete|skip)
timestamp       TEXT
source          TEXT
```

### `daily_agg`
```sql
id              INTEGER PRIMARY KEY
habit_id        INTEGER
day             TEXT
completions     INTEGER DEFAULT 0
skips           INTEGER DEFAULT 0
UNIQUE(habit_id, day)
```

## 🔧 Configuration

### Environment Variables (optional)

Create a `.env` file:
```bash
FLASK_DEBUG=1  # Enable debug mode
DATABASE_PATH=habits.db
```

Or run with debug flag:
```bash
flask run --debug
```

### Database Initialization

Database and tables are created automatically on first run via `init_db()` and `ensure_tables()`.

## 📱 Android Integration

Update the base URL in your Android app's API service:

```kotlin
object RetrofitInstance {
    private const val BASE_URL = "http://YOUR_SERVER_IP:5000/"
    // For emulator: http://10.0.2.2:5000/
    // For local device: http://YOUR_LOCAL_IP:5000/
}
```

## 🧪 Testing

Quick API test with curl:

```bash
# Create habit
curl -X POST http://127.0.0.1:5000/habits \
  -H "Content-Type: application/json" \
  -d '{"name":"Read daily","description":"Read for 15 min"}'

# Get all habits
curl http://127.0.0.1:5000/habits

# Log completion event
curl -X POST http://127.0.0.1:5000/events \
  -H "Content-Type: application/json" \
  -d '{"habit_id":1,"event_type":"complete","source":"manual"}'

# Get analytics
curl http://127.0.0.1:5000/analytics
```

## 🚨 Known Limitations

- **SQLite Concurrency**: Limited write concurrency (mitigated with timeouts and busy_timeout PRAGMA)
- **Development Server**: Use production WSGI server (gunicorn/waitress) for deployment
- **No Authentication**: Currently no user authentication (single-user app)

## 🔄 Production Deployment

For production, use a WSGI server:

```bash
# Install gunicorn
pip install gunicorn

# Run with gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## 📝 License

MIT License - feel free to use this project for learning or personal use.

## 🤝 Contributing

This is a personal project, but suggestions and improvements are welcome!

1. Fork the repo
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📧 Contact

For questions or issues, open an issue on GitHub.

---

**Built with ❤️ for habit tracking enthusiasts**
