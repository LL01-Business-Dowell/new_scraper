import os
import torch
from django.apps import AppConfig
from transformers import AutoConfig, Wav2Vec2ForSequenceClassification, AutoFeatureExtractor
from huggingface_hub import hf_hub_download
import os
import torch

# Prevent PyTorch from spawning thread floods that trigger Gunicorn OOM/Timeouts
torch.set_num_threads(1)
torch.set_num_interop_threads(1)

class AudioanalyticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "AudioAnalytics"

    predictor_model = None
    feature_extractor = None
    device = None

    def ready(self):
        model_id = "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition"

        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )

        print("--> Loading preprocessor configurations...")
        self.feature_extractor = AutoFeatureExtractor.from_pretrained(model_id)

        print("--> Downloading and patching legacy acoustic weights...")
        try:
            # 1. Load the structural configuration profile
            config = AutoConfig.from_pretrained(model_id)
            config.classifier_proj_size = 1024
            
            # 2. Instantiate an uninitialized modern target model instance
            model = Wav2Vec2ForSequenceClassification(config)

            # 3. Securely pull the binary checkpoint file into local cache
            try:
                # Try downloading modern safetensors format first
                weights_path = hf_hub_download(repo_id=model_id, filename="model.safetensors")
                from safetensors.torch import load_file
                state_dict = load_file(weights_path)
            except Exception:
                # Fallback to PyTorch bin format if safetensors is unavailable
                weights_path = hf_hub_download(repo_id=model_id, filename="pytorch_model.bin")
                state_dict = torch.load(weights_path, map_location="cpu")

            # 4. Map legacy naming convention properties to modern equivalents
            key_mapping = {
                "classifier.dense.weight": "projector.weight",
                "classifier.dense.bias": "projector.bias",
                "classifier.output.weight": "classifier.weight",
                "classifier.output.bias": "classifier.bias"
            }

            # Map the tensors over
            patched_state_dict = {}
            for key, value in state_dict.items():
                if key in key_mapping:
                    patched_state_dict[key_mapping[key]] = value
                else:
                    patched_state_dict[key] = value

            # 5. Load the patched weights cleanly into the PyTorch structure
            loading_info = model.load_state_dict(patched_state_dict, strict=True)
            print(f"--> Weight mapping complete: {loading_info}")

            # 6. Assign the patched model to your Django configuration state and move to device
            self.predictor_model = model.to(self.device)
            self.predictor_model.eval()

            print(f"✓ Patched audio model loaded successfully on {self.device}!")

        except Exception as e:
            print(f"❌ Critical Error loading audio model: {str(e)}")