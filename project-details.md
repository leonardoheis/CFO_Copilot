# Project Scoping Questions for ML Software Development  

## 1. Problem Definition

### What real-world problem are you addressing, and why is it important? 

### Who are the target users or stakeholders of your system?  

### Is the problem supervised, unsupervised, reinforcement, or a hybrid ML task? Choose one and explain

## 2. Data Considerations  

### What kind of data will you use (structured, unstructured, multimodal)?  

### Do you already have access to the data? (Yes/No) - If not, look for a dataset you have access to.

### Can the data be used openly in academic projects? (Yes/No) - If not, look for a different dataset.

### What is the expected size and quality of the dataset? Does the data require cleaning?

## 3. System Design & Software Architecture  

### Which technology would you like to use for the different components of the ML Pipeline?

#### Frontend

- [ ] Streamlit (recommended)
- [ ] Gradio
- [ ] FastHTML
- [ ] Other

#### REST API

- [ ] FastAPI (recommended)
- [ ] Flask
- [ ] Django-Rest
- [ ] Other

#### Experiment Tracking

- [ ] MLFlow
- [ ] Weights and Biases (recommended)
- [ ] Neptune
  
#### Hyperparameter Tuning

- [ ] Optuna (recommended)
- [ ] HyperOpt
- [ ] Tune

#### Dataprocessing Library

- [ ] Pandas
- [ ] Polars
- [ ] PySpark
- [ ] Narwhals

#### Machine Learning Framework

- [ ] Scikit Learn (recommended)
- [ ] FastAI
- [ ] Keras
- [ ] Pytorch Lightning
- [ ] PyMC

#### SQL Database

- [ ] Supabase (recommended)
- [ ] Vercel (Postgres)
- [ ] Other

#### NoSQL Database (Optional)

- [ ] Firebase (recommended)
- [ ] Other

#### Storage

- [ ] Supabase Blobs (recommended)
- [ ] Other

#### Testing Framework

- [ ] Pytest (recommended)
- [ ] Unittest


## 4. Model Development & Lifecycle  

### Do you plan to build models from scratch or leverage pre-trained models?  

### What criteria will you use to define model success beyond accuracy (e.g., fairness, latency, robustness)?  

## 5. Testing & Quality Assurance  

### How will you test your system end-to-end, especially around ML-specific challenges (e.g., non-determinism, drift)?  

## 6. Deployment & Operations  

### Will your system run in batch mode, real-time, or hybrid?  

### How will you monitor the system for performance degradation and data drift?  

