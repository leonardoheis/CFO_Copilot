import uvicorn

if __name__ == "__main__":
    uvicorn.run("src.app.api:create_app", factory=True)
