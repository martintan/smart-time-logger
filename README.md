# ActivityWatch Timeline Processor

A Python CLI tool that fetches timeline data from ActivityWatch API and processes it using LLM to create clean, consolidated time blocks suitable for time tracking platforms.

## Quick Start

```bash
python time.py
```

When the interactive prompt appears, type natural language commands or notes and press Enter. The CLI shows the estimated LLM token cost beneath the prompt; press `Ctrl+T` at any time to accept and run the consolidation immediately, press `Ctrl+Y` to copy the full LLM payload to your clipboard, or submit an empty line to skip.

> Tip: For the clipboard shortcut to copy to your system clipboard, install the optional `pyperclip` package (`pip install pyperclip`). Otherwise the CLI falls back to an in-memory clipboard.

## Features

- 🔗 Connect to local ActivityWatch instance
- ⏰ Interactive time selection (hourly intervals)
- 📊 Fetch timeline data from all available buckets
- 🤖 Process timeline with LLM (LiteLLM `gpt-5-nano` by default)
- 🧮 Preview estimated LLM input tokens before processing
- ⌨️ Interactive command prompt with Ctrl+T quick action and Ctrl+Y prompt copy
- 🧼 Automatically filters AFK ActivityWatch events and sorts timelines chronologically to keep prompts concise
- 📋 Generate clean, grouped time blocks
- 💾 Save results to file
- 🎨 Rich CLI interface with tables and colors

## Installation

### Prerequisites

1. **ActivityWatch**: Make sure ActivityWatch is installed and running on your system

   - Download from: <https://activitywatch.net/>
   - Default runs on `http://localhost:5600`

2. **Python 3.8+**: Ensure you have Python 3.8 or later installed

### Setup

1. **Clone or create the project directory:**

   ```bash
   mkdir aw-timeline-processor
   cd aw-timeline-processor
   ```

2. **Create virtual environment:**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Linux/Mac
   # or
   venv\Scripts\activate     # On Windows
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables for LiteLLM:**

   ```bash
   export OPENAI_API_KEY="your-openai-api-key-here"
   ```

   Or create a `.env` file:

   ```
   OPENAI_API_KEY=your-openai-api-key-here
   ```

## Requirements File

Create a `requirements.txt` file with these dependencies:

```
requests>=2.31.0
litellm>=1.44.0
click>=8.1.0
rich>=13.7.0
python-dotenv>=1.0.0
```

## Usage

### Basic Usage

Run the CLI tool:

```bash
python time.py
```

### Configuration

The CLI runs with sensible defaults out of the box. You can tweak behaviour by setting environment variables before executing `python time.py`:

- `LLM_MODEL`: override the consolidation model (defaults to `gpt-5-nano`).
- `AW_SERVER_URL`: point to a different ActivityWatch server (defaults to `http://localhost:5600`).
- `MIN_ACTIVITY_DURATION_MINUTES`: discard consolidated blocks shorter than this value (defaults to `5`).
- `SNAPSHOT_ENABLED` (in `time.py`): toggle ActivityWatch snapshot persistence (defaults to `False`).

### Interactive Flow

1. **Connection Test**: Verifies connection to ActivityWatch
2. **Bucket Discovery**: Shows available data buckets
3. **Time Selection**: Interactive menu to select start time (hourly intervals)
4. **Data Fetching**: Retrieves timeline events from all buckets
5. **LLM Processing**: Consolidates timeline into clean time blocks
6. **Results Display**: Shows processed timeline with optional file save

## Example Output

The LLM will process your raw ActivityWatch data and output structured time blocks like:

```json
{
  "summary": "Productive morning session focused on development work with some communication",
  "time_blocks": [
    {
      "start_time": "09:00",
      "end_time": "10:30",
      "duration_minutes": 90,
      "activity": "Code development in VS Code - Python project",
      "category": "Work"
    },
    {
      "start_time": "10:30",
      "end_time": "10:45",
      "duration_minutes": 15,
      "activity": "Email and Slack communication",
      "category": "Communication"
    }
  ],
  "total_tracked_time": "105 minutes"
}
```

## Troubleshooting

### ActivityWatch Connection Issues

- Ensure ActivityWatch is running: Check if you can access `http://localhost:5600` in your browser
- Verify the correct port: ActivityWatch might be running on a different port
- Check firewall settings

### LLM Processing Issues

- Verify your OpenAI API key is set correctly
- Check if you have sufficient API credits
- Try using a different model (e.g., `gpt-3.5-turbo`)

### No Timeline Data

- Make sure ActivityWatch has been running and collecting data
- Check the selected time range - pick a time when you were active
- Verify your system clock is correct

## Configuration

You can modify the following in the script:

- **Default model**: Change `default='gpt-4'` to your preferred model
- **Default duration**: Change `default=1` to your preferred hour duration
- **API timeout**: Modify `timeout=5` in the connection test
- **Event limit**: Adjust `limit=1000` in the get_events method

## Next Steps

This tool prepares timeline data for input into time tracking platforms. The structured output can be easily:

- Imported into time tracking tools like Toggl, Clockify, or Harvest
- Converted to CSV for spreadsheet analysis
- Integrated with project management tools
- Used for automated time logging workflows

## License

This project is open source. Feel free to modify and distribute.
