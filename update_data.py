from nsepython import nse_get_advances_declines
import json
import os

def fetch_market_data():
    try:
        # Fetching Advances and Declines as a sample data point
        data = nse_get_advances_declines()
        
        # Adding a timestamp so you know when it last updated
        from datetime import datetime
        final_data = {
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": data
        }

        with open('data.json', 'w') as f:
            json.dump(final_data, f)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fetch_market_data()