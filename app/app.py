from collections import defaultdict
import uuid, requests, random, json
from flask import Flask, request, redirect, url_for, jsonify, app, render_template, flash, Response
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_login import LoginManager, current_user, AnonymousUserMixin, login_user, logout_user, login_required
from flask_migrate import Migrate
from models import db, User, Project, APIKey, APICall, APIResponse, OpenAIModel, ModelCost, InternalAPIKey
from werkzeug.exceptions import Unauthorized, Forbidden
from werkzeug.urls import url_parse
from forms import LoginForm, ModelCostForm, OpenAIModelForm, ProjectForm, APIKeyForm, APIResponseFilterForm
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db' # Use SQLite for simplicity
app.config['SECRET_KEY'] = '2e3368c5ee5bd49c9635924c55bd22277bddebcd379c662b'

db.init_app(app)

migrate = Migrate(app, db)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

class AdminModelView(ModelView):
    def is_accessible(self):
        if current_user.get_id() == None:
            return False
        return current_user.is_authenticated and current_user.is_admin
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))

class ProjectAdminModelView(ModelView):
    def is_accessible(self):
        if current_user.get_id() == None:
            return False
        return current_user.is_authenticated and current_user.is_admin or current_user.is_project_admin
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))

with app.app_context():
    db.create_all()
    admin = Admin(app, name='API Proxy', template_mode='bootstrap3')
    admin.add_view(AdminModelView(User, db.session))
    admin.add_view(ProjectAdminModelView(APIKey, db.session, name="Open API Keys"))
    admin.add_view(ProjectAdminModelView(Project, db.session,))
    admin.add_view(ProjectAdminModelView(APICall, db.session, name="API Calls"))
    admin.add_view(ProjectAdminModelView(APIResponse, db.session, name="API Responses"))
    admin.add_view(ProjectAdminModelView(OpenAIModel, db.session, name="OpenAI Model"))
    admin.add_view(ProjectAdminModelView(ModelCost, db.session, name="Model cost"))
    admin.add_view(ProjectAdminModelView(InternalAPIKey, db.session, name="Internal API Key"))

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password')
            return redirect(url_for('login'))
        login_user(user)
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('home')
        return redirect(next_page)
    return render_template('login.html', title='Sign In', form=form)

@app.route('/')
@app.route('/home')
@login_required
def home():
    projects = get_users_projects()
    for p in projects:
        print(p, p.users.all())
    api_keys = APIKey.query.filter(APIKey.user_id == current_user.id).all()
    return render_template('home.html', projects=projects, api_keys=api_keys)

def get_users_projects():
    if current_user.is_admin:
        return Project.query.all()
    return current_user.projects
    
@login_required
@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/new/project', methods=['GET', 'POST'])
def new_project():
    form = ProjectForm()
    form.api_key.choices = [(key.id, key.name) for key in APIKey.query.filter(APIKey.user_id == current_user.id).all()]
    form.users.choices = [(user.id, user.username) for user in User.query.all()]
    form.project_leads.choices = [(user.id, user.username) for user in User.query.all()]
    form.allowed_models.choices = [(model.id, model.name) for model in OpenAIModel.query.all()]
    form.spending_limit.data = 0
    if form.validate_on_submit():
        project = Project(name=form.name.data, spending_limit=form.spending_limit.data)
        project.users = User.query.filter(User.id.in_(form.users.data)).all()
        project.project_leads = User.query.filter(User.id.in_(form.project_leads.data)).all()
        project.allowed_models = OpenAIModel.query.filter(OpenAIModel.id.in_(form.allowed_models.data)).all()
        project.api_key_id = form.api_key.data
        db.session.add(project)
        db.session.commit()
        all_users = []
        all_users.extend(project.users)
        all_users.extend(project.lead_users)
        all_users = list(set(all_users)) # remove potential duplicates
        for u in project.users:
            key = InternalAPIKey(user_id = u.id, project_id = project.id)
            key_string = str(uuid.uuid4())
            key.internal_api_key_string = key_string
            db.session.add(key)
        db.session.commit()
        flash('Your project has been created!', 'success')
        return redirect(url_for('home'))
    return render_template('new_project.html', title='New Project', form=form)

@app.route('/new/model', methods=['GET', 'POST'])
def new_model():
    model_form = OpenAIModelForm()
    cost_form = ModelCostForm()
    if model_form.validate_on_submit() and cost_form.validate_on_submit():
        model = OpenAIModel(name=model_form.name.data)
        db.session.add(model)
        db.session.commit()
        cost = ModelCost(model_id=model.id,
                         in_tokens_cost=cost_form.in_tokens_cost.data,
                         out_tokens_cost=cost_form.out_tokens_cost.data,
                         start_date=cost_form.start_date.data,
                         end_date=cost_form.end_date.data)
        db.session.add(cost)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('new_model.html', model_form=model_form, cost_form=cost_form)

@app.route('/new/api_key', methods=['GET', 'POST'])
def new_api_key():
    form = APIKeyForm()
    if form.validate_on_submit():
        api_key = form.key_string.data
        headers = {"Authorization": f"Bearer {api_key}"}
        data = {"input": "test", "model": "text-embedding-ada-002"}
        response = requests.post('https://api.openai.com/v1/embeddings', headers=headers, json=data)
        if response.status_code != 200:
            flash('Error: {}'.format(response.json()['error']), 'error')
            return redirect(url_for('new_api_key'))

        new_key = APIKey(name=form.name.data, key_string=form.key_string.data, user_id=current_user.id)
        db.session.add(new_key)
        db.session.commit()
        flash('Your API key has been created.', 'success')
        return redirect(url_for('home'))
    return render_template('new_api_key.html', form=form)

@app.route('/view_model/<model_id>', methods=['GET'])
def view_model(model_id):
    model = OpenAIModel.query.filter_by(id=model_id).first()
    if not model:
        flash("That model does not exist")
        return redirect(url_for('home'))
    current_cost = model.get_current_cost()
    outdated_costs = model.get_outdated_costs()
    future_costs = model.get_future_costs()
    return render_template('view_model.html', model=model, current_cost=current_cost, outdated_costs=outdated_costs, future_costs=future_costs)


@app.route('/project/<int:project_id>/activity', methods=['GET', 'POST'])
def api_responses(project_id):
    project = db.session.query(Project).get(project_id)
    all_users = []
    all_users.extend(project.users)
    all_users.extend(project.lead_users)
    all_users = list(set(all_users))  # remove potential duplicates
    form = APIResponseFilterForm()
    form.users.choices = [(u.id, u.username) for u in all_users]
    responses = {}
    total_costs = {'tokens_in': 0, 'tokens_out': 0}  # to store total costs
    model_costs = defaultdict(lambda: {'tokens_in': 0, 'tokens_out': 0})  # to store costs per model
    if request.method == 'POST':
        print(form.data)
        start_date = form.start_date.data
        end_date = form.end_date.data
        users = [int(n) for n in form.users.data]
        model_name = None
        # Get the projects associated with the given user (or all projects if no user is specified)
        key_filters = []
        if users != []:
            key_filters.append(InternalAPIKey.user_id.in_(form.users.data))
        internal_api_keys = project.internal_api_keys.all() if len(key_filters) == 0 else project.internal_api_keys.filter(*key_filters).all()
        api_response_filters = []
        if start_date:
            api_response_filters.append(APIResponse.time_created >= start_date)
        if end_date:
            api_response_filters.append(APIResponse.time_created <= end_date)
        if model_name:  # filter api responses by model name if given
            api_response_filters.append(APIResponse.model_name == model_name)
        for internal_api_key in internal_api_keys:
            # Get the API responses for the key within the date range
            api_responses = internal_api_key.api_responses.filter(*api_response_filters).all()
            for api_response in api_responses:
                # Aggregate the data by day, user and model
                day = api_response.time_created.strftime('%Y-%m-%d')
                username = api_response.internal_api_key.user.username
                model_name = api_response.model_name
                if day not in responses:
                    responses[day] = {
                        'total': {'tokens_in': 0, 'tokens_out': 0, 'cost': {'in_cost': 0, 'out_cost': 0}},
                        'users': defaultdict(lambda: defaultdict(lambda: {'tokens_in': 0, 'tokens_out': 0, 'cost': {'in_cost': 0, 'out_cost': 0}}))
                    }
                responses[day]['users'][username][model_name]['tokens_in'] += api_response.tokens_in
                responses[day]['users'][username][model_name]['tokens_out'] += api_response.tokens_out
                cost = api_response.get_costs()  # calculate cost
                if cost is not None:  # if costs could be calculated
                    responses[day]['users'][username][model_name]['cost']['in_cost'] += cost['in_cost']
                    responses[day]['users'][username][model_name]['cost']['out_cost'] += cost['out_cost']
                    responses[day]['total']['tokens_in'] += api_response.tokens_in
                    responses[day]['total']['tokens_out'] += api_response.tokens_out
                    responses[day]['total']['cost']['in_cost'] += cost['in_cost']
                    responses[day]['total']['cost']['out_cost'] += cost['out_cost']
                    total_costs['tokens_in'] += cost['in_cost']  # sum total costs
                    total_costs['tokens_out'] += cost['out_cost']
                    model_costs[model_name]['tokens_in'] += cost['in_cost']  # sum costs per model
                    model_costs[model_name]['tokens_out'] += cost['out_cost']
    return render_template('project_activity.html', form=form, responses=responses, total_costs=total_costs, model_costs=model_costs)


@app.route('/change_price/<model_id>', methods=['POST'])
def change_price(model_id):
    new_price_in = request.form.get('in_tokens_cost')
    new_price_out = request.form.get('out_tokens_cost')
    new_start_date = request.form.get('start_date')  # We expect this in the format 'YYYY-MM-DD'
    new_start_date = datetime.strptime(new_start_date, '%Y-%m-%d')
    # Get model
    model = OpenAIModel.query.get(model_id)
    # Find and update current cost object
    current_cost = model.get_current_cost()
    current_cost.end_date = new_start_date - timedelta(days=1)
    # Create new cost object
    new_cost = ModelCost(model_id=model.id, in_tokens_cost=new_price_in, out_tokens_cost=new_price_out, start_date=new_start_date)
    db.session.add(new_cost)
    db.session.commit()
    return redirect(url_for('view_model', model_id=model.id))

@app.route('/delete_cost/<cost_id>', methods=['POST'])
def delete_cost(cost_id):
    cost = ModelCost.query.get(cost_id)
    if cost is None:
        flash("that cost object does not exist")
        return redirect(url_for('home'))
        # handle cost not found, maybe redirect to error page
    model_id = cost.model_id
    model = OpenAIModel.query.get(model_id)
    # Find the current cost object
    current_cost = model.get_current_cost()
    # Get the next future cost
    next_cost = model.get_future_costs().first()
    if next_cost is not None and next_cost.id != cost.id:
        # There is another future cost, fill in the gap
        current_cost.end_date = next_cost.start_date - timedelta(days=1)
    else:
        # No other future costs, set the end date of the current cost object to None
        current_cost.end_date = None
    db.session.delete(cost)
    db.session.commit()
    return redirect(url_for('view_model', model_id=model_id))

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

if __name__ == '__main__':
    app.run(debug=True)



##### This is to handle the logic of the actual end points

@app.errorhandler(Unauthorized)
def handle_unauthorized(e):
    return jsonify({'error': str(e)}), 401

@app.errorhandler(Forbidden)
def handle_forbidden(e):
    return jsonify({'error': str(e)}), 403


def require_api_key(view_function):
    @wraps(view_function)
    def decorator(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        token = None
        if not auth_header:
            raise Unauthorized('No Authorization header')
        try:
            auth_type, token = auth_header.split()
            if auth_type.lower() != 'bearer':
                raise Unauthorized('Invalid Authorization type')
        except ValueError:
            raise Unauthorized('Invalid Authorization header')
        ik = InternalAPIKey.get_by_string(token)
        if not ik.is_current():
            raise Forbidden("Your API key is not current")
        proj = ik.project
        if proj.total_spent > proj.spending_limit * .98 and proj.spending_limit != 0:
            raise Forbidden("Your project is out of money")
        if ik.total_spent > ik.spending_limit * .98 and ik.spending_limit != 0:
            raise Forbidden("Your API key is out of money")
        api_key = APIKey.query.filter(APIKey.id == proj.api_key_id).first().key_string
        request.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        return view_function(*args, **kwargs)
    return decorator


@app.route('/v1/chat/completions', methods=['POST'])
@require_api_key
def chat_completions():
    url = '/v1/chat/completions'
    return requests.post(url, headers=request.headers, data=request.data)

@app.route('/v1/embeddings', methods=['POST'])
@require_api_key
def embeddings():
    url = '/v1/embeddings'
    return requests.post(url, headers=request.headers, data=request.data)

@app.route('/v1/completions', methods=['POST'])
@require_api_key
def completions():
    url = f"https://api.openai.com/{request.url_rule.endpoint}"
    resp = requests.post(url, headers=request.headers, data=request.data)
    flask_resp = Response(response=resp.content, status=resp.status_code, headers=dict(resp.headers))
    return flask_resp

@app.route('/v1/audio/transcriptions', methods=['POST'])
@require_api_key
def audio_transcriptions():
    url = '/v1/audio/transcriptions'
    return jsonify(200, requests.post(url, headers=request.headers, data=request.data))

@app.route('/v1/audio/translations', methods=['POST'])
def audio_translations():
    url = '/v1/audio/translations'
    return requests.post(url, headers=request.headers, data=request.data)


def generate_random_time():
    start_date = datetime(2023, 6, 1)
    end_date = datetime(2023, 7, 27)
    time_between_dates = end_date - start_date
    random_number_of_seconds = random.randint(0, int(time_between_dates.total_seconds()))
    random_date = start_date + timedelta(seconds=random_number_of_seconds)
    return random_date

@app.route('/add_test_data')
def add_test_data():
    for n in ["Kenneth", "Kristoffer", "Ida", "Lisa"]:
        u = User(username=n)
        db.session.add(u)
        db.session.commit()
    api_key = APIKey(name="Test APIKey", user_id = 1)
    db.session.add(api_key)
    db.session.commit()
    db.session.commit()
    p = Project(name="Arthur test project", api_key_id = api_key.id, allowed_models=OpenAIModel.query.all(), users=User.query.all())
    db.session.add(p)
    db.session.commit()
    for u in p.users:
        ik = InternalAPIKey(user_id = u.id, project_id = p.id)
        db.session.add(ik)
    db.session.commit()
    for ik in p.internal_api_keys:
        for n in range(400):
            print(ik.user.username)
            model_name = random.sample(p.model_names(), 1)[0]
            in_tokens = random.randint(5, 400)
            out_tokens = random.randint(5, 400)
            response = APIResponse(model_name = model_name, tokens_in = in_tokens, tokens_out = out_tokens, internal_api_key_id = ik.id, time_created = generate_random_time())
            db.session.add(response)
            db.session.commit()
    return redirect(url_for('home'))

@app.route('/init_db')
def init_db():
    u = User(username="Arthur", is_admin=True)
    u.set_password("Hermes_2014")
    db.session.add(u)
    db.session.commit()
    for d in model_costs():
        m = OpenAIModel(name=d['model_name'], description=d['description'])
        db.session.add(m)
        db.session.commit()
        mc = ModelCost(model_id = m.id, in_tokens_cost=d['input_cost'], out_tokens_cost=d['output_cost'], start_date = datetime(2021, 1, 1))
        db.session.add(mc)
        db.session.commit()
    return redirect(url_for('home'))


def model_costs():
    costs = [
        {'model_name': 'gpt-4', 'description': 'chat', 'input_cost': 0.03, 'output_cost': 0.06},
        {'model_name': 'gpt-4-0613', 'description': 'chat', 'input_cost': 0.03, 'output_cost': 0.06},
        {'model_name': 'gpt-4-32k', 'description': 'chat', 'input_cost': 0.06, 'output_cost': 0.12},
        {'model_name': 'gpt-4-32k-0613', 'description': 'chat', 'input_cost': 0.06, 'output_cost': 0.12},
        {'model_name': 'gpt-3.5-turbo', 'description': 'chat', 'input_cost': 0.0015, 'output_cost': 0.002},
        {'model_name': 'gpt-3.5-turbo-0613', 'description': 'chat', 'input_cost': 0.0015, 'output_cost': 0.002},
        {'model_name': 'gpt-3.5-turbo-16k', 'description': 'chat', 'input_cost': 0.003, 'output_cost' : 0.003},
        {'model_name': 'gpt-3.5-turbo-16k-0613', 'description': 'chat', 'input_cost': 0.003, 'output_cost' : 0.003},
        {'model_name': 'text-davinci-003', 'description': 'text completion', 'input_cost': 0.03, 'output_cost': 0.12},
        {'model_name': 'text-davinci-002', 'description': 'text completion', 'input_cost': 0.03, 'output_cost': 0.12},
        {'model_name': 'text-davinci-001', 'description': 'text completion', 'input_cost': 0.03, 'output_cost': 0.12},
        {'model_name': 'text-curie-001', 'description': 'text completion', 'input_cost': 0.003, 'output_cost': 0.012},
        {'model_name': 'text-babbage-001', 'description': 'text completion', 'input_cost': 0.0006, 'output_cost': 0.0024},
        {'model_name': 'text-ada-001', 'description': 'text completion', 'input_cost': 0.0004, 'output_cost': 0.0016},
        {'model_name': 'davinci', 'description': 'fine-tuning', 'input_cost': 0.03, 'output_cost': 0.12},
        {'model_name': 'curie', 'description': 'fine-tuning', 'input_cost': 0.003, 'output_cost': 0.012},
        {'model_name': 'babbage', 'description': 'fine-tuning', 'input_cost': 0.0006, 'output_cost': 0.0024},
        {'model_name': 'ada', 'description': 'fine-tuning', 'input_cost': 0.0004, 'output_cost': 0.0016},
        {'model_name': 'text-embedding-ada-002', 'description': 'embeddings', 'input_cost': 0.0001, 'output_cost' : 0.0001}
    ]
    return costs