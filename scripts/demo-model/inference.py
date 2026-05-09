
import json

def model_fn(model_dir):
    return {'status': 'loaded'}

def input_fn(request_body, content_type):
    return json.loads(request_body)

def predict_fn(input_data, model):
    return {'prediction': 'demo', 'input': input_data}

def output_fn(prediction, accept):
    return json.dumps(prediction)
