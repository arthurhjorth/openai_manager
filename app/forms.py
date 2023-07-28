from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectMultipleField, IntegerField, DateTimeField, SelectField
from wtforms.validators import DataRequired
from wtforms.fields import DateTimeLocalField
from datetime import datetime

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Sign In')

class ProjectForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    api_key = SelectField('Choose which OpenAI API key to use for this project', coerce=int)
    spending_limit = IntegerField('Spending Limit ($US). Leave at 0 for no spending limit.')
    users = SelectMultipleField('Users', coerce=int)
    project_leads = SelectMultipleField('Project Leads', coerce=int)
    allowed_models = SelectMultipleField('Allowed Models', coerce=int)
    submit = SubmitField('Submit')

class OpenAIModelForm(FlaskForm):
    name = StringField('Model Name. This name must exactly match the name of the model on OpenAI', validators=[DataRequired()])
    submit = SubmitField('Submit')

class ModelCostForm(FlaskForm):
    in_tokens_cost = IntegerField('In Tokens Cost per 1,000 tokens (US$)', validators=[DataRequired()])
    out_tokens_cost = IntegerField('Out Tokens Cost per 1,000 tokens (US$)', validators=[DataRequired()])
    start_date = DateTimeField('Start Date', default=datetime.utcnow, validators=[DataRequired()])
    end_date = DateTimeField('End Date, leave blank if current')

class APIKeyForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    key_string = StringField('API Key', validators=[DataRequired()])
    submit = SubmitField('Submit')

class APIResponseFilterForm(FlaskForm):
    users = SelectMultipleField('Users (leave blank for everybody).')
    models = SelectMultipleField('Models (leave blank for everybody).')
    start_date = DateTimeLocalField('Start Date', format='%Y-%m-%dT%H:%M')
    end_date = DateTimeLocalField('End Date', format='%Y-%m-%dT%H:%M')
    submit = SubmitField('Submit')