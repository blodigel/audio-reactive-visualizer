from app.config import config
from app.main import app
import uvicorn

if __name__ == "__main__":
    uvicorn.run(app, host=config.host, port=config.port)
