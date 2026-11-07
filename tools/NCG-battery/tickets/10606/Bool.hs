module Bool where
bool :: a -> a -> Bool -> a
bool f t b = case b of
  False -> f
  True  -> t
