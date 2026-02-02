from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ocr_lang: str = "eng"
    ocr_timeout_seconds: int = 15
    model_path: str = "models/vendor_classifier.pt"
    device: str = "cpu"


settings = Settings()
