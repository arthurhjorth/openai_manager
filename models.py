from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON, and_, or_, desc

db = SQLAlchemy()

from werkzeug.security import generate_password_hash, check_password_hash

# Define the association tables for the many-to-many relationships
projects_users = db.Table('projects_users',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('project_id', db.Integer, db.ForeignKey('project.id'))
)

project_leads = db.Table('project_leads',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('project_id', db.Integer, db.ForeignKey('project.id'))
)

# Many-to-many relationship between Project and OpenAIModel
projects_models = db.Table('projects_models',
    db.Column('project_id', db.Integer, db.ForeignKey('project.id')),
    db.Column('open_ai_model_id', db.Integer, db.ForeignKey('open_ai_model.id'))
)

class APIKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128))
    key_string = db.Column(db.String(128), index=True, unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    time_created = db.Column(db.DateTime, default=datetime.utcnow)
    projects = db.relationship('Project', backref='api_key', lazy='dynamic')  # new line
    

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    time_created = db.Column(db.DateTime, default=datetime.utcnow)
    email = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, default=False)
    is_project_admin = db.Column(db.Boolean, default=False)
    api_keys = db.relationship('APIKey', backref='user')
    projects = db.relationship('Project', secondary=projects_users, backref=db.backref('users', lazy='dynamic'))
    lead_projects = db.relationship('Project', secondary=project_leads, backref=db.backref('lead_users', lazy='dynamic'))

    def __str__(self):
        return self.username

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), index=True, unique=True)
    time_created = db.Column(db.DateTime, default=datetime.utcnow)
    api_key_id = db.Column(db.Integer, db.ForeignKey('api_key.id')) 
    spending_limit = db.Column(db.Float, default = 0)
    total_spent = db.Column(db.Float, default = 0)
    allowed_models = db.relationship('OpenAIModel', secondary=projects_models, backref=db.backref('projects', lazy='dynamic'))
    internal_api_keys = db.relationship('InternalAPIKey', backref='project', lazy='dynamic')
    
    def model_names(self):
        return [m.name for m in self.allowed_models]


    def update_spending(self):
        for internal_api_key in self.internal_api_keys:
            # Fetch all the APIResponse objects once
            api_responses = APIResponse.query.filter(
                APIResponse.internal_api_key_id == internal_api_key.id,
                APIResponse.time_created > internal_api_key.spending_last_checked
            ).all()
            # Find the most recent time_created among these APIResponses
            latest_time_created = max([api_response.time_created for api_response in api_responses], default=None)
            # Now calculate and update the spending for this InternalAPIKey
            for api_response in api_responses:
                cost = api_response.get_costs()
                if cost:  # Make sure the cost was actually computed
                    internal_api_key.total_spent += cost['total_cost']
            # Update the spending_last_checked to the most recent time_created
            if latest_time_created:
                internal_api_key.spending_last_checked = latest_time_created
        # Now, update the Project.total_spent to reflect the sum of total_spent of all its internal_api_keys
        self.total_spent = sum([internal_api_key.total_spent for internal_api_key in self.internal_api_keys])


class OpenAIModel(db.Model):
    __tablename__ = 'open_ai_model'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), index=True, unique=True, nullable=False)
    description = db.Column(db.String(128), index=True, nullable=False)
    costs = db.relationship('ModelCost', backref='model', lazy='dynamic')
    
    def get_current_cost(self):
        return self.costs.filter(or_(ModelCost.end_date == None, ModelCost.start_date <= datetime.utcnow(), ModelCost.end_date > datetime.utcnow())).first()
    def get_outdated_costs(self):
        return self.costs.filter(ModelCost.end_date <= datetime.utcnow()).order_by(desc(ModelCost.end_date))
    def get_future_costs(self):
        return self.costs.filter(ModelCost.start_date > datetime.utcnow()).order_by(ModelCost.start_date)


class ModelCost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Foreign key for one to many relationship
    model_id = db.Column(db.Integer, db.ForeignKey('open_ai_model.id'))
    in_tokens_cost = db.Column(db.Integer, nullable=False)
    out_tokens_cost = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    end_date = db.Column(db.DateTime, nullable=True)


class APIResponse(db.Model):
    __tablename__ = 'api_response'
    id = db.Column(db.Integer, primary_key=True)
    model_name = db.Column(db.String(64))
    tokens_in = db.Column(db.Integer)
    tokens_out = db.Column(db.Integer)
    internal_api_key_id = db.Column(db.Integer, db.ForeignKey('internal_api_key.id')) 
    request = db.Column(JSONB)
    response = db.Column(JSONB)
    time_created = db.Column(db.DateTime, default=datetime.utcnow)
    in_cost = db.Column(db.Float)
    out_cost = db.Column(db.Float)

    def update_cost(self):
        # Get the relevant OpenAIModel
        open_ai_model = OpenAIModel.query.filter_by(name=self.model_name).first()
        current_cost = open_ai_model.get_current_cost()
        # Compute the costs
        self.in_cost = self.tokens_in * current_cost.in_tokens_cost / 1000 # price is in per 1k tokens
        self.out_cost = self.tokens_out * current_cost.out_tokens_cost / 1000


    def get_costs(self):
        # Get the relevant OpenAIModel
        open_ai_model = OpenAIModel.query.filter_by(name=self.model_name).first()

        if not open_ai_model:
            return None  # or you may want to raise an exception

        # Query the ModelCost instances for this OpenAIModel
        # that were valid at the time of this APIResponse
        model_cost = ModelCost.query.filter(
            ModelCost.model_id == open_ai_model.id,
            and_(ModelCost.start_date <= self.time_created, 
                 or_(ModelCost.end_date >= self.time_created, ModelCost.end_date.is_(None)))
        ).first()
        if not model_cost:
            return None  

        # Compute the costs
        in_cost = self.tokens_in * model_cost.in_tokens_cost
        out_cost = self.tokens_out * model_cost.out_tokens_cost
        return {'in_cost': in_cost, 'out_cost': out_cost, 'total_cost' : in_cost+out_cost}


class InternalAPIKey(db.Model):
    __tablename__ = 'internal_api_key'
    id = db.Column(db.Integer, primary_key=True)
    internal_api_key_string = db.Column(db.String(128), unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', backref='internal_api_keys')
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime, nullable=True)
    spending_limit = db.Column(db.Float, default=0.0)
    total_spent = db.Column(db.Float, default=0)
    spending_last_checked = db.Column(db.DateTime)
    time_created = db.Column(db.DateTime, default=datetime.utcnow)
    api_responses = db.relationship('APIResponse', backref='internal_api_key', lazy='dynamic')

    @classmethod
    def get_by_string(cls, astr):
        return db.session.query(cls).filter(cls.internal_api_key_string==astr).first()

    def is_current(self):
        today = datetime.utcnow()
        if self.end_date is None:
            return today >= self.start_date
        else:
            return self.start_date <= today <= self.end_date