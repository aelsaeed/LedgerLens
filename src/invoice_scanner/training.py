from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from invoice_scanner.utils import ensure_parent


@dataclass
class TrainingConfig:
    epochs: int = 2
    batch_size: int = 8
    lr: float = 1e-3
    model_path: Path = Path("models/vendor_classifier.pt")


class DummyVendorDataset(Dataset):
    def __init__(self) -> None:
        self.samples = [
            ("Acme Corp", 0),
            ("Globex", 1),
            ("Umbrella", 2),
            ("Acme Corp", 0),
        ]
        self.vocab = {word: idx for idx, word in enumerate({"acme", "globex", "umbrella"})}

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        name, label = self.samples[idx]
        vector = torch.zeros(len(self.vocab))
        token = name.split()[0].lower()
        vector[self.vocab[token]] = 1.0
        return vector, label


class VendorClassifier(nn.Module):
    def __init__(self, input_dim: int, num_classes: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 8),
            nn.ReLU(),
            nn.Linear(8, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def train(config: TrainingConfig) -> None:
    dataset = DummyVendorDataset()
    loader = DataLoader(dataset, batch_size=config.batch_size, shuffle=True)

    model = VendorClassifier(input_dim=len(dataset.vocab), num_classes=3)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.lr)
    criterion = nn.CrossEntropyLoss()

    model.train()
    for _ in range(config.epochs):
        for features, labels in loader:
            optimizer.zero_grad()
            logits = model(features)
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()

    ensure_parent(config.model_path)
    torch.save({"state_dict": model.state_dict(), "vocab": dataset.vocab}, config.model_path)
    print(f"Saved model to {config.model_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=2)
    args = parser.parse_args()

    train(TrainingConfig(epochs=args.epochs))


if __name__ == "__main__":
    main()
