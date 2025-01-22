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


# Modele
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
    options = db.relationship('Option', backref='poll', lazy=True)


class Option(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(200), nullable=False)
    votes = db.Column(db.Integer, default=0)
    correct = db.Column(db.Boolean, default=False)
    poll_id = db.Column(db.String(36), db.ForeignKey('poll.id'), nullable=False)


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
    #db.drop_all()  # Șterge toate tabelele
    db.create_all()  # Crează noile tabele cu schema actualizată


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    errors = []  # Initialize an empty list to store error messages

    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']

        # Check if email already exists
        if User.query.filter_by(email=email).first():
            errors.append("Email already used!")

        # Check if username already exists
        if User.query.filter_by(username=username).first():
            errors.append("Username already exists!")

        # Validate password (at least one uppercase and one digit)
        if len(password) < 8 or not re.search(r'[A-Z]', password) or not re.search(r'\d', password):
            errors.append(
                "Password must be at least 8 characters long, contain at least one uppercase letter, and one digit!")

        # If there are no errors, create the new user
        if not errors:
            hashed_password = generate_password_hash(password)
            new_user = User(email=email, username=username, password=hashed_password)
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('login'))

    # Render the form with errors if any
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
        correct_options = request.form.getlist('correct_options[]')  # Contains indices of correct options

        user = User.query.filter_by(username=session['username']).first()
        poll_id = str(uuid.uuid4())
        new_poll = Poll(id=poll_id, title=title, creator=user)
        db.session.add(new_poll)

        for i, option_text in enumerate(options):
            is_correct = str(i) in correct_options  # Compare with the checkbox index
            option = Option(text=option_text, poll=new_poll, correct=is_correct)
            db.session.add(option)

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

    is_creator = False
    user = User.query.filter_by(username=session['username']).first()
    if user and poll.creator_id == user.id:
        is_creator = True

    existing_vote = Vote.query.filter_by(user_id=user.id, poll_id=poll.id).first()
    has_voted = existing_vote is not None

    if request.method == 'POST':
        if not is_creator and not has_voted:
            selected_option_ids = request.form.getlist('options')

            # Group options based on headings
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

            total_correct = 0
            for group in grouped_options:
                section_correct = True
                if group[0].text.startswith('<h1>'):
                    for option in group[1:]:
                        if str(option.id) in selected_option_ids and not option.correct:
                            section_correct = False
                            break
                    if section_correct:
                        for option in group[1:]:
                            if str(option.id) in selected_option_ids and option.correct:
                                total_correct += 1

            for group in grouped_options:
                if not group[0].text.startswith('<h1>'):
                    for option in group:
                        if str(option.id) in selected_option_ids and option.correct:
                            total_correct += 1
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
    print(f"Debugging: Options for poll {poll.id}: {[option.text for option in poll.options]}")
    return render_template('poll.html', poll=poll, is_creator=is_creator, has_voted=has_voted)

@app.route('/delete/<poll_id>', methods=['GET'])
def delete_poll(poll_id):
    # Check if the user is logged in
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    if not user:
        return redirect(url_for('login'))

    # Get the poll to delete
    poll = Poll.query.get(poll_id)
    if not poll:
        return "Poll not found!"

    # Ensure the logged-in user is the creator of the poll
    if poll.creator_id != user.id:
        return "You are not the creator of this poll!"

    # Delete related votes
    Vote.query.filter_by(poll_id=poll_id).delete()

    # Delete options associated with the poll
    Option.query.filter_by(poll_id=poll_id).delete()

    # Delete the poll itself
    db.session.delete(poll)
    db.session.commit()

    return redirect(url_for('dashboard'))


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

    # Get all votes for the poll
    votes = Vote.query.filter_by(poll_id=poll.id).all()

    # Group votes by user
    user_votes = {}
    for vote in votes:
        if vote.user_id not in user_votes:
           user_votes[vote.user_id] = []
        user_votes[vote.user_id].append(vote)

    # Calculate correct counts for each user, considering section logic
    vote_details = {}
    for user_id, votes_list in user_votes.items():
        user = User.query.get(user_id)
        if not user:
            continue

        correct_count = 0

        # Create the same grouped options
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


        # Function to check if an option was selected in the user's votes for a specific poll
        def is_option_selected(option_id, vote_list):
            for vote in vote_list:
                if vote.option_id == option_id:
                   return True
            return False
        total_correct = 0
        # Calculate score based on grouped options logic
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

        vote_details[user.username] = {
            'options': [Option.query.get(vote.option_id).text for vote in votes_list],
            'correct_count': correct_count+ total_correct
        }
    # Convert the vote_details dictionary into a list of dictionaries for easier rendering
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

    # Get all votes by the current user
    votes = Vote.query.filter_by(user_id=user.id).all()

    # Group votes by poll
    poll_votes = {}
    for vote in votes:
        if vote.poll_id not in poll_votes:
            poll_votes[vote.poll_id] = []
        poll_votes[vote.poll_id].append(vote)

    # Calculate correct counts for each poll, considering section logic
    poll_results = {}
    for poll_id, votes_list in poll_votes.items():
        poll = Poll.query.get(poll_id)
        if not poll:
            continue

        correct_count = 0
        # Create the same grouped options
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

        # Function to check if an option was selected in the user's votes for a specific poll
        def is_option_selected(option_id, vote_list):
            for vote in vote_list:
                if vote.option_id == option_id:
                    return True
            return False
        total_correct = 0
        # Calculate score based on grouped options logic
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