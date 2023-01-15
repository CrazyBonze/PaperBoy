FROM python:3.10


#RUN curl -sSL https://install.python-poetry.org | python -
RUN pip install poetry
# Configuring poetry
RUN poetry config virtualenvs.create false

# Copying requirements of a project
COPY pyproject.toml poetry.lock /app/src/
WORKDIR /app/src


# Installing requirements
RUN poetry install

# Copying actuall application
COPY . /app/src/

CMD ["poetry", "run", "python", "paperboy"]
