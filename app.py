from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import re

app = Flask(__name__)
app.secret_key = 'secret'

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///polls.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    polls = db.relationship('Poll', backref='creator', lazy=True)

class Poll(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_private = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    options = db.relationship('Option', backref='poll', lazy=True)
    access = db.relationship('PollAccess', backref='poll', lazy=True)

class Option(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(200), nullable=False)
    votes = db.Column(db.Integer, default=0)
    correct = db.Column(db.Boolean, default=False)
    poll_id = db.Column(db.String(36), db.ForeignKey('poll.id'), nullable=False)

class PollAccess(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.String(36), db.ForeignKey('poll.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    poll_id = db.Column(db.String(36), db.ForeignKey('poll.id'), nullable=False)
    option_id = db.Column(db.Integer, db.ForeignKey('option.id'), nullable=False)
    is_correct = db.Column(db.Boolean, default=False)

    user = db.relationship('User', backref=db.backref('votes', lazy=True))
    poll = db.relationship('Poll', backref=db.backref('votes', lazy=True))
    option = db.relationship('Option', backref=db.backref('option_votes', lazy=True))

with app.app_context():
    #db.drop_all()
    db.create_all()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    errors = []

    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']

        if User.query.filter_by(email=email).first():
            errors.append("Email already used!")
        if User.query.filter_by(username=username).first():
            errors.append("Username already exists!")
        if len(password) < 8 or not re.search(r'[A-Z]', password) or not re.search(r'\d', password):
            errors.append("Password must be at least 8 characters long, contain at least one uppercase letter, and one digit!")

        if not errors:
            hashed_password = generate_password_hash(password)
            new_user = User(email=email, username=username, password=hashed_password)
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('login'))

    return render_template('register.html', errors=errors)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['username'] = username
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            return "Invalid credentials!"

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    polls = Poll.query.filter_by(creator_id=user.id).all()
    return render_template('dashboard.html', polls=polls)

@app.route('/create_poll', methods=['GET', 'POST'])
def create_poll():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        options = request.form.getlist('options')
        correct_options = request.form.getlist('correct_options[]')


        private_flag = request.form.get('private')
        is_private = True if private_flag == 'on' else False

        user = User.query.filter_by(username=session['username']).first()
        poll_id = str(uuid.uuid4())
        new_poll = Poll(id=poll_id, title=title, creator=user, is_private=is_private)
        db.session.add(new_poll)


        for i, option_text in enumerate(options):
            is_correct = str(i) in correct_options
            option = Option(text=option_text, poll=new_poll, correct=is_correct)
            db.session.add(option)

        db.session.commit()


        if is_private:
            allowed_usernames = request.form.getlist("allowed_users")
            for username in allowed_usernames:
                username = username.strip()
                if username:
                    allowed_user = User.query.filter_by(username=username).first()
                    if allowed_user:
                        access = PollAccess(poll_id=new_poll.id, user_id=allowed_user.id)
                        db.session.add(access)
            db.session.commit()

        return redirect(url_for('dashboard'))

    return render_template('create_poll.html')

@app.route('/poll/<poll_id>', methods=['GET', 'POST'])
def poll(poll_id):
    poll = Poll.query.get(poll_id)
    if not poll:
        return "Poll not found!"

    if 'username' not in session:
        return redirect(url_for('login', next=url_for('poll', poll_id=poll_id)))

    user = User.query.filter_by(username=session['username']).first()


    if poll.is_private and poll.creator_id != user.id:
        allowed_ids = [access.user_id for access in poll.access]
        if user.id not in allowed_ids:
            return "Access denied! This poll is private."

    is_creator = (user and poll.creator_id == user.id)
    existing_vote = Vote.query.filter_by(user_id=user.id, poll_id=poll.id).first()
    has_voted = existing_vote is not None

    if request.method == 'POST':
        if not poll.is_active:
            return "This poll is closed for answers."

        if not is_creator and not has_voted:
            selected_option_ids = request.form.getlist('options')
            if len(selected_option_ids) > 0:
                for selected_option_id in selected_option_ids:
                    option = Option.query.get(selected_option_id)
                    if option:
                        option.votes += 1
                        new_vote = Vote(user_id=user.id, poll_id=poll.id, option_id=selected_option_id,
                                        is_correct=option.correct)
                        db.session.add(new_vote)
            db.session.commit()
        return redirect(url_for('poll', poll_id=poll_id))
    return render_template('poll.html', poll=poll, is_creator=is_creator, has_voted=has_voted)

@app.route('/delete/<poll_id>', methods=['GET'])
def delete_poll(poll_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    if not user:
        return redirect(url_for('login'))

    poll = Poll.query.get(poll_id)
    if not poll:
        return "Poll not found!"

    if poll.creator_id != user.id:
        return "You are not the creator of this poll!"

    Vote.query.filter_by(poll_id=poll_id).delete()
    Option.query.filter_by(poll_id=poll_id).delete()
    PollAccess.query.filter_by(poll_id=poll_id).delete()
    db.session.delete(poll)
    db.session.commit()

    return redirect(url_for('dashboard'))

@app.route('/poll/<poll_id>/stop_answers', methods=['GET'])
def stop_answers(poll_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    poll = Poll.query.get(poll_id)
    if not poll:
        return "Poll not found!"
    if poll.creator_id != user.id:
        return "You are not the creator of this poll!"

    poll.is_active = False
    db.session.commit()
    return redirect(url_for('poll', poll_id=poll_id))

@app.route('/poll/<poll_id>/results')
def poll_results(poll_id):
    poll = Poll.query.get(poll_id)
    if not poll:
        return "Poll not found!"

    if 'username' not in session:
        return "Access denied!"

    user = User.query.filter_by(username=session['username']).first()
    if not user or poll.creator_id != user.id:
        return "Access denied!"

    votes = Vote.query.filter_by(poll_id=poll.id).all()
    user_votes = {}
    for vote in votes:
        if vote.user_id not in user_votes:
            user_votes[vote.user_id] = []
        user_votes[vote.user_id].append(vote)

    vote_details = {}
    for user_id, votes_list in user_votes.items():
        user_obj = User.query.get(user_id)
        if not user_obj:
            continue

        correct_count = 0

        grouped_options = []
        current_group = []
        for option in poll.options:
            if option.text.startswith('<h1>'):
                if current_group:
                    grouped_options.append(current_group)
                current_group = [option]
            else:
                current_group.append(option)
        if current_group:
            grouped_options.append(current_group)

        def is_option_selected(option_id, vote_list):
            for vote in vote_list:
                if vote.option_id == option_id:
                    return True
            return False

        total_correct = 0
        for group in grouped_options:
            section_correct = True
            if group[0].text.startswith('<h1>'):
                for option in group[1:]:
                    if is_option_selected(option.id, votes_list) and not option.correct:
                        section_correct = False
                        break
                if section_correct:
                    for option in group[1:]:
                        if is_option_selected(option.id, votes_list) and option.correct:
                            total_correct += 1

        for group in grouped_options:
            if not group[0].text.startswith('<h1>'):
                for option in group:
                    if is_option_selected(option.id, votes_list) and option.correct:
                        correct_count += 1

        vote_details[user_obj.username] = {
            'options': [Option.query.get(vote.option_id).text for vote in votes_list],
            'correct_count': correct_count + total_correct
        }

    grouped_votes = [
        {'username': username, 'options': details['options'], 'correct_count': details['correct_count']}
        for username, details in vote_details.items()
    ]

    return render_template('results.html', poll=poll, grouped_votes=grouped_votes)

@app.route('/user_results')
def user_results():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    if not user:
        return "User not found"

    votes = Vote.query.filter_by(user_id=user.id).all()
    poll_votes = {}
    for vote in votes:
        if vote.poll_id not in poll_votes:
            poll_votes[vote.poll_id] = []
        poll_votes[vote.poll_id].append(vote)

    poll_results = {}
    for poll_id, votes_list in poll_votes.items():
        poll = Poll.query.get(poll_id)
        if not poll:
            continue

        correct_count = 0
        grouped_options = []
        current_group = []
        for option in poll.options:
            if option.text.startswith('<h1>'):
                if current_group:
                    grouped_options.append(current_group)
                current_group = [option]
            else:
                current_group.append(option)
        if current_group:
            grouped_options.append(current_group)

        def is_option_selected(option_id, vote_list):
            for vote in vote_list:
                if vote.option_id == option_id:
                    return True
            return False

        total_correct = 0
        for group in grouped_options:
            section_correct = True
            if group[0].text.startswith('<h1>'):
                for option in group[1:]:
                    if is_option_selected(option.id, votes_list) and not option.correct:
                        section_correct = False
                        break
                if section_correct:
                    for option in group[1:]:
                        if is_option_selected(option.id, votes_list) and option.correct:
                            total_correct += 1

        for group in grouped_options:
            if not group[0].text.startswith('<h1>'):
                for option in group:
                    if is_option_selected(option.id, votes_list) and option.correct:
                        correct_count += 1

        poll_results[poll_id] = {
            'title': poll.title,
            'correct_count': correct_count + total_correct
        }

    results_list = list(poll_results.values())
    return render_template('user_results.html', results=results_list)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
