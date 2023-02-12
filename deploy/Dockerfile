FROM python:3.10

# Install poetry package manager
RUN pip install poetry

# Configure poetry to not create virtual environments
RUN poetry config virtualenvs.create false

# Copy project dependencies
COPY pyproject.toml poetry.lock /app/src/

# Set working directory
WORKDIR /app/src

# Install project dependencies
RUN poetry install

# Copy application code
COPY . /app/src/

# Run application
CMD ["poetry", "run", "python", "paperboy"]
