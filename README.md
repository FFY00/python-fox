# python-fox

Fast automated task runner. Usually used as a test runner.


### Usage

Create a `foxfile.py`:
```python
import fox


@fox.task()
def something():
    print('something!')
```

```
$ fox
> executing something
something!
```
