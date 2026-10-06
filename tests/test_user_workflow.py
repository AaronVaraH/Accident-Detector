import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from inference_sdk import InferenceHTTPClient, InferenceConfiguration
from config import settings

client = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key=settings.ROBOFLOW_API_KEY,
).configure(InferenceConfiguration(api_key_transport="header"))

# Probar el workflow original del usuario
try:
    result = client.run_workflow(
        workspace_name="aaron-vara",
        workflow_id="general-segmentation-api",
        images={"image": "https://images.unsplash.com/photo-1542385151-efd9000785a0?w=640&q=80"},
        parameters={"classes": "fire, smoke"},
        use_cache=True,
    )
    print("Resultado del workflow general-segmentation-api:")
    print(result)
except Exception as e:
    print("Error ejecutando workflow:", e)
